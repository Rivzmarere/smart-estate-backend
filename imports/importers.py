"""
Loading an estate's existing records from a spreadsheet.

    homes       gated estate: stands, homes, owners, residents and levy owed
    properties  rental portfolio: properties, owners, tenants, leases and rent owed
    balances    either: what each home or tenant owed (or had in credit) on the day you start

An import is all or nothing. Every row is checked first; if any row has a
problem nothing is saved and the office gets the list of problems by row
number, so they fix the spreadsheet and upload it again. A check ("preview")
does exactly the same work and then throws it away, so what it reports is
what the real import will do.

Nothing is sent to anyone: no SMS, WhatsApp or receipts.
"""

import copy
import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from home.models import Home
from levy.models import Invoice, Payment, money
from owner.models import Owner
from parameters.models.models_home_status import HomeStatus
from parameters.models.models_stand_status import StandStatus
from rentals import services as rentals
from rentals.models import Lease
from resident.models import Resident
from stand.models import Stand
from visit.utilities import phone_variants

from .models import ImportBatch
from .reader import Column, clean, squash

log = logging.getLogger(__name__)
ZERO = Decimal("0.00")
PREVIEW_ROWS = 300
BROUGHT_FORWARD = "Balance brought forward"


def full_name(person):
    return f"{person.name} {person.surname}".strip()


def status(model, names):
    """The shared status with one of these names (first that exists), created if the list has none."""
    for name in names:
        found = model.objects.filter(name__iexact=name, status=True).first()
        if found:
            return found
    return model.objects.create(name=names[0])


@dataclass
class Result:
    rows: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    preview: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    created: dict = field(default_factory=dict)
    ignored_columns: list = field(default_factory=list)
    batch: object = None

    def count(self, key, by=1):
        self.counts[key] = self.counts.get(key, 0) + by

    def made(self, obj):
        label = obj._meta.label_lower
        self.created.setdefault(label, []).append(obj.pk)
        return obj

    def as_dict(self):
        counts = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.counts.items()}
        return {
            "rows": self.rows,
            "ok": not self.errors,
            "errors": self.errors[:500],
            "error_count": len(self.errors),
            "warnings": self.warnings[:500],
            "warning_count": len(self.warnings),
            "preview": self.preview,
            "counts": counts,
            "ignored_columns": self.ignored_columns,
            "batch": self.batch.pk if self.batch else None,
        }


class RowProblem(Exception):
    def __init__(self, message, column=None):
        super().__init__(message)
        self.column = column


# ---------------------------------------------------------------- shared columns

def person_columns(prefix, who, required, phone_required=False):
    title = who.capitalize()
    return [
        Column(f"{prefix}_name", f"{title} first name", required=required, example="", max_length=60,
               aliases=(f"{who} name", f"{who} firstname", f"{who} first names", f"{who} names", f"{who} forename")),
        Column(f"{prefix}_surname", f"{title} surname", required=required, max_length=60,
               aliases=(f"{who} last name", f"{who} lastname", f"{who} family name")),
        Column(f"{prefix}_phone", f"{title} mobile", kind="phone", required=phone_required,
               aliases=(f"{who} phone", f"{who} cell", f"{who} cellphone", f"{who} phone number", f"{who} mobile number",
                        f"{who} contact", f"{who} whatsapp")),
        Column(f"{prefix}_email", f"{title} email", kind="email", max_length=60, aliases=(f"{who} email address", f"{who} e-mail")),
        Column(f"{prefix}_id", f"{title} ID number", max_length=20, aliases=(f"{who} id", f"{who} national id", f"{who} id no")),
    ]


BALANCE_DATE = Column("as_at", "Balance date", kind="date", aliases=("as at", "as of", "balance as at", "date"),
                      help="The day the balance is correct on. Empty: today.")


class Importer:
    kind = ""
    title = ""
    estate_kinds = ()
    columns = []
    sheet_title = "Data"
    examples = []
    notes = []

    def __init__(self, estate, user, today=None):
        self.estate = estate
        self.user = user
        self.today = today or timezone.localdate()
        self.result = Result()
        self._owners = {}
        self._residents = {}
        self._statuses = {}

    # ---- running

    def run(self, sheet, commit=False, filename=""):
        self.result.ignored_columns = sheet.ignored_columns
        self.result.rows = len(sheet.rows)
        with transaction.atomic():
            self.prepare(sheet.rows)
            for line, raw in sheet.rows:
                values, problems = clean(self.columns, raw)
                for key, problem in problems.items():
                    self.error(line, f"{self.header(key)} {problem}", key)
                if problems:
                    continue
                saved = self._snapshot()
                try:
                    with transaction.atomic():
                        preview = self.row(line, values)
                except RowProblem as exc:
                    self._restore(saved)
                    self.error(line, str(exc), exc.column)
                    continue
                except Exception as exc:  # a database rule we did not check for: report it on the row
                    log.exception("Import row %s failed", line)
                    self._restore(saved)
                    self.error(line, f"This row could not be saved ({exc.__class__.__name__}). Check its values.")
                    continue
                if preview and len(self.result.preview) < PREVIEW_ROWS:
                    self.result.preview.append({"row": line, **preview})
            if self.result.errors or not commit:
                transaction.set_rollback(True)
            else:
                self.result.batch = ImportBatch.objects.create(
                    kind=self.kind, filename=filename[:200], rows=self.result.rows,
                    summary=self.result.as_dict()["counts"], created_ids=self.result.created, created_by=self.user,
                )
        return self.result

    def prepare(self, rows):
        pass

    def _snapshot(self):
        # A row that fails is rolled back, so forget anything it created or counted.
        return (dict(self._owners), dict(self._residents), dict(self._statuses),
                copy.deepcopy(self.result.counts), copy.deepcopy(self.result.created), self._extra_state())

    def _restore(self, saved):
        self._owners, self._residents, self._statuses, self.result.counts, self.result.created, extra = saved
        self._restore_extra(extra)

    def _extra_state(self):
        return None

    def _restore_extra(self, extra):
        pass

    def row(self, line, values):
        raise NotImplementedError

    # ---- reporting

    def header(self, key):
        return next((c.header for c in self.columns if c.key == key), key)

    def error(self, line, message, key=None):
        self.result.errors.append({"row": line, "column": self.header(key) if key else "", "message": message})

    def warn(self, line, message, key=None):
        self.result.warnings.append({"row": line, "column": self.header(key) if key else "", "message": message})

    # ---- people

    def _find(self, model, cache, phone):
        if not phone:
            return None
        if phone in cache:
            return cache[phone]
        found = model.objects.filter(phone_number1__in=phone_variants(phone), status=True).order_by("id").first()
        cache[phone] = found
        return found

    def _check_same(self, person, values, prefix, role):
        wanted = squash(values[f"{prefix}_name"] + values[f"{prefix}_surname"])
        if wanted and squash(person.name + person.surname) != wanted:
            raise RowProblem(
                f"The mobile {person.phone_number1} already belongs to {full_name(person)} ({role}). "
                "Check the number, or use the same name on every row for this person.",
                f"{prefix}_phone",
            )

    def owner(self, values, prefix="owner"):
        """The owner on this row: an existing one with the same mobile, or a new one."""
        phone = values[f"{prefix}_phone"]
        found = self._find(Owner, self._owners, phone)
        if found:
            self._check_same(found, values, prefix, "an owner")
            return found, False
        owner = self.result.made(Owner.objects.create(
            name=values[f"{prefix}_name"], surname=values[f"{prefix}_surname"], id_number=values[f"{prefix}_id"],
            phone_number1=phone, email=values[f"{prefix}_email"], authorized_by=self.user,
        ))
        self._owners[phone] = owner
        self.result.count("owners")
        return owner, True

    def resident(self, values, prefix, role="a resident"):
        phone = values[f"{prefix}_phone"]
        found = self._find(Resident, self._residents, phone)
        if found:
            self._check_same(found, values, prefix, role)
            return found
        person = self.result.made(Resident.objects.create(
            name=values[f"{prefix}_name"], surname=values[f"{prefix}_surname"], id_number=values[f"{prefix}_id"],
            phone_number1=phone or None, email=values[f"{prefix}_email"] or None, authorized_by=self.user,
        ))
        if phone:
            self._residents[phone] = person
        self.result.count("residents" if prefix == "resident" else "tenants")
        return person

    def status(self, model, *names):
        key = (model, names)
        if key not in self._statuses:
            self._statuses[key] = status(model, list(names))
        return self._statuses[key]

    # ---- balances

    def as_at(self, values, line):
        day = values.get("as_at") or self.today
        if day > self.today:
            raise RowProblem("The balance date is in the future.", "as_at")
        return day

    def brought_forward(self, home, balance, day, lease=None):
        """
        What was owed (or paid ahead) before Smart Estate. Owed: an invoice due the day
        before the balance date, so it counts as arrears at once. In credit: a credit,
        not counted as money collected.
        """
        if not balance:
            return
        if balance > 0:
            when = day - datetime.timedelta(days=1)
            self.result.made(Invoice.objects.create(
                home=home, lease=lease, stand_number=home.stand.stand_number, address=home.address, kind=Invoice.OPENING,
                description=f"{BROUGHT_FORWARD} (owed on {day:%d %b %Y})", amount_usd=money(balance),
                issued_on=when, due_date=when, created_by=self.user,
            ))
            self.result.count("owed_usd", money(balance))
            self.result.count("owing")
        else:
            paid_at = timezone.make_aware(datetime.datetime.combine(day, datetime.time(0, 0)))
            self.result.made(Payment.objects.create(
                home=home, lease=lease, currency=Payment.USD, amount=money(-balance), amount_usd=money(-balance),
                method=Payment.OPENING, status=Payment.PAID, paid_at=paid_at, recorded_by=self.user,
                note=f"Credit brought forward (on {day:%d %b %Y})",
            ))
            self.result.count("credit_usd", money(-balance))
            self.result.count("in_credit")


# ---------------------------------------------------------------- gated estates

class HomesImport(Importer):
    kind = "homes"
    title = "Homes, owners and residents"
    estate_kinds = ("estate",)
    sheet_title = "Homes"
    columns = [
        Column("stand", "Stand number", kind="int", required=True, aliases=("stand", "stand no", "stand #", "plot", "plot number", "unit", "unit number", "house number")),
        Column("address", "Address", required=True, max_length=200, aliases=("street address", "house address", "physical address")),
        *person_columns("owner", "owner", required=True, phone_required=True),
        Column("owner_lives", "Owner lives here", kind="yes", aliases=("owner occupied", "owner resident", "lives here"),
               help="Yes when the owner lives in the home (then the resident columns can stay empty)."),
        *person_columns("resident", "resident", required=False),
        Column("balance", "Levy owed (USD)", kind="money", aliases=("balance", "levy owed", "arrears", "amount owed", "balance owed", "levy balance", "owed"),
               help="What the home owed on the balance date. Negative (e.g. -50) if they paid ahead. Empty or 0 if nothing."),
        BALANCE_DATE,
    ]
    examples = [
        ["101", "101 Acacia Drive", "Tendai", "Ncube", "0772 123 456", "tendai@example.com", "63-123456A42", "Yes", "", "", "", "", "", "45", ""],
        ["102", "102 Acacia Drive", "Precious", "Chiwenga", "0712 345 678", "", "", "No", "Farai", "Dube", "0773 222 333", "", "", "0", ""],
        ["103", "103 Acacia Drive", "Precious", "Chiwenga", "0712 345 678", "", "", "No", "", "", "", "", "", "-20", ""],
    ]
    notes = [
        "One row per home. Starred columns must be filled in.",
        "An owner with several homes: repeat the same name and mobile on each row. They are added once.",
        "Owner lives here = Yes makes the owner the resident. Otherwise fill in the resident (tenant), or leave it empty for an empty home.",
        "Levy owed: what the home owed on the balance date, before Smart Estate. Negative if they paid ahead.",
        "Mobile numbers can be written 0772 123 456, +263 772 123 456 or 263772123456.",
    ]

    def prepare(self, rows):
        self._stands = {}

    def row(self, line, v):
        number = v["stand"]
        if number <= 0:
            raise RowProblem("The stand number must be more than 0.", "stand")
        if number in self._stands:
            raise RowProblem(f"Stand {number} is also on row {self._stands[number]}. Each home needs its own stand number.", "stand")
        self._stands[number] = line
        stand = Stand.objects.filter(stand_number=number, status=True).first()
        if stand:
            home = Home.objects.filter(stand=stand, status=True).first()
            if home:
                raise RowProblem(f"Stand {number} is already in the system ({home.address}).", "stand")

        resident_given = any(v[k] for k in ("resident_name", "resident_surname", "resident_phone", "resident_email", "resident_id"))
        if resident_given and not (v["resident_name"] and v["resident_surname"]):
            raise RowProblem("Give the resident's first name and surname, or leave all the resident columns empty.", "resident_name")
        if v["owner_lives"] and resident_given and squash(v["resident_name"] + v["resident_surname"]) != squash(v["owner_name"] + v["owner_surname"]):
            raise RowProblem("Owner lives here is Yes but a different resident is given. Use one or the other.", "owner_lives")

        owner, _ = self.owner(v)
        if v["owner_lives"] and not resident_given:
            for key in ("name", "surname", "phone", "email", "id"):
                v[f"resident_{key}"] = v[f"owner_{key}"]
            resident_given = True
        resident = self.resident(v, "resident") if resident_given else None
        if resident and not resident.phone_number1:
            self.warn(line, "No mobile for the resident: they cannot use WhatsApp, SMS or USSD until one is added.", "resident_phone")

        owner_occupied = bool(resident) and squash(full_name(resident)) == squash(full_name(owner))
        if not stand:
            stand = self.result.made(Stand.objects.create(
                stand_number=number, authorized_by=self.user,
                stand_status=self.status(StandStatus, "Occupied") if resident else self.status(StandStatus, "Vacant", "Unoccupied"),
            ))
            self.result.count("stands")
        if not resident:
            home_status = self.status(HomeStatus, "Vacant", "Unoccupied")
        elif owner_occupied:
            home_status = self.status(HomeStatus, "Owner occupied", "Occupied")
        else:
            home_status = self.status(HomeStatus, "Rented", "Occupied")
        home = self.result.made(Home.objects.create(
            owner=owner, stand=stand, address=v["address"], resident=resident, home_status=home_status, authorized_by=self.user,
        ))
        self.result.count("homes")
        self.brought_forward(home, v["balance"], self.as_at(v, line))
        return {
            "reference": number, "address": home.address, "owner": full_name(owner),
            "occupant": full_name(resident) if resident else "", "state": home_status.name,
            "balance": str(v["balance"] or ZERO),
        }


# ---------------------------------------------------------------- rental portfolios

class PropertiesImport(Importer):
    kind = "properties"
    title = "Properties, tenants and leases"
    estate_kinds = ("rental",)
    sheet_title = "Properties"
    columns = [
        Column("reference", "Reference", kind="int", aliases=("ref", "property number", "property no", "number", "unit number", "stand number"),
               help="The property's number. Empty: numbered for you."),
        Column("address", "Address", required=True, max_length=200, aliases=("property", "property address", "unit", "street address")),
        *person_columns("owner", "owner", required=True, phone_required=True),
        *person_columns("tenant", "tenant", required=False),
        Column("rent", "Monthly rent (USD)", kind="money", aliases=("rent", "rent usd", "monthly rent", "rental")),
        Column("start", "Lease start", kind="date", aliases=("start date", "lease start date", "moved in", "start")),
        Column("end", "Lease end", kind="date", aliases=("end date", "lease end date", "lease expiry", "expiry"),
               help="Empty: month to month."),
        Column("due_day", "Rent due day", kind="int", aliases=("due day", "day due", "rent due"), help="Day of the month rent is due (1 to 28). Empty: the 1st."),
        Column("deposit", "Deposit (USD)", kind="money", aliases=("deposit", "deposit usd", "deposit required")),
        Column("deposit_paid", "Deposit paid (USD)", kind="money", aliases=("deposit paid", "deposit received", "deposit held"),
               help="Empty: the whole deposit was paid."),
        Column("balance", "Rent owed (USD)", kind="money", aliases=("balance", "arrears", "rent owed", "amount owed", "balance owed", "owed"),
               help="Rent owed from before this month. Negative if paid ahead. This month's rent is billed by Smart Estate."),
        BALANCE_DATE,
    ]
    examples = [
        ["1", "Flat 3, Baines Court, 12 Baines Avenue, Avenues", "Tawanda", "Makoni", "0772 900 100", "", "", "Rudo", "Moyo", "0771 000 201", "", "", "450", "2024-03-01", "2027-02-28", "1", "450", "", "900", ""],
        ["2", "14 Quorn Avenue, Mount Pleasant", "Tawanda", "Makoni", "0772 900 100", "", "", "Tendai", "Ncube", "0771 000 202", "", "", "900", "2025-01-01", "", "5", "900", "900", "0", ""],
        ["3", "Unit 3, 88 Kaguvi Street, CBD (shop)", "Precious", "Chiwenga", "0712 345 678", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]
    notes = [
        "One row per property. Starred columns must be filled in.",
        "A landlord with several properties: repeat the same name and mobile on each row. A landlord running their own portfolio puts their own name as the owner.",
        "A let property: fill in the tenant, the monthly rent and the lease start. An empty property: leave the tenant columns empty.",
        "Rent owed: what the tenant owed from before this month. Smart Estate bills this month's rent itself. Negative if they paid ahead.",
        "Dates can be written 2025-03-31 or 31/03/2025.",
    ]

    def prepare(self, rows):
        self._refs = {}
        given = []
        for _, raw in rows:
            values, problems = clean(self.columns[:1], raw)
            if "reference" not in problems and values.get("reference"):
                given.append(values["reference"])
        top = Stand.objects.aggregate(top=Max("stand_number"))["top"] or 0
        self._next = max([top, *given]) + 1

    def _extra_state(self):
        return self._next

    def _restore_extra(self, extra):
        self._next = extra

    def row(self, line, v):
        number = v["reference"]
        if number is not None:
            if number <= 0:
                raise RowProblem("The reference must be more than 0.", "reference")
            if number in self._refs:
                raise RowProblem(f"Reference {number} is also on row {self._refs[number]}.", "reference")
            if Stand.objects.filter(stand_number=number, status=True).exists():
                home = Home.objects.filter(stand__stand_number=number, status=True).first()
                raise RowProblem(f"Reference {number} is already in the system" + (f" ({home.address})." if home else "."), "reference")
        else:
            number = self._next
            self._next += 1
        self._refs[number] = line

        let = any(v[k] for k in ("tenant_name", "tenant_surname", "tenant_phone", "tenant_email", "tenant_id"))
        if let:
            if not (v["tenant_name"] and v["tenant_surname"]):
                raise RowProblem("Give the tenant's first name and surname, or leave all the tenant columns empty.", "tenant_name")
            if not v["rent"] or v["rent"] <= 0:
                raise RowProblem("A let property needs the monthly rent.", "rent")
            if not v["start"]:
                raise RowProblem("A let property needs the date the lease started.", "start")
            if v["end"] and v["end"] < v["start"]:
                raise RowProblem("The lease ends before it starts.", "end")
            if v["due_day"] is not None and not 1 <= v["due_day"] <= 28:
                raise RowProblem("The rent due day must be from 1 to 28.", "due_day")
            for key in ("deposit", "deposit_paid"):
                if v[key] is not None and v[key] < 0:
                    raise RowProblem("The deposit cannot be negative.", key)
        else:
            filled = [self.header(k) for k in ("rent", "start", "end", "deposit", "deposit_paid") if v[k]]
            if filled:
                raise RowProblem(f"{', '.join(filled)} given but no tenant. Fill in the tenant, or clear those columns.", "tenant_name")
            if v["balance"]:
                raise RowProblem("An empty property cannot owe rent. Put the balance on the row of the tenant who owes it.", "balance")

        owner, _ = self.owner(v)
        stand = self.result.made(Stand.objects.create(
            stand_number=number, authorized_by=self.user,
            stand_status=self.status(StandStatus, "Occupied") if let else self.status(StandStatus, "Vacant", "Unoccupied"),
        ))
        home = self.result.made(Home.objects.create(
            owner=owner, stand=stand, address=v["address"], home_status=self.status(HomeStatus, "Vacant", "Unoccupied"),
            authorized_by=self.user,
        ))
        self.result.count("properties")
        preview = {"reference": number, "address": home.address, "owner": full_name(owner), "occupant": "", "state": "Vacant", "balance": "0.00"}
        if not let:
            return preview

        tenant = self.resident(v, "tenant", role="a tenant")
        if not tenant.phone_number1:
            self.warn(line, "No mobile for the tenant: they cannot get rent reminders, WhatsApp or USSD until one is added.", "tenant_phone")
        deposit = v["deposit"] or ZERO
        try:
            lease = rentals.start_lease(
                home, tenant, user=self.user, first_rent_usd=ZERO, start_date=v["start"], end_date=v["end"],
                rent_usd=money(v["rent"]), due_day=v["due_day"] or 1, deposit_usd=money(deposit),
                deposit_paid_usd=money(deposit if v["deposit_paid"] is None else v["deposit_paid"]),
            )
        except rentals.LeaseError as exc:
            raise RowProblem(str(exc))
        self.result.made(lease)
        self.result.count("leases")
        if v["end"] and v["end"] < self.today:
            self.warn(line, f"The lease ended on {v['end']:%d %b %Y}. It stays active until you end or renew it.", "end")
        # This month's rent: billed now, as the rent job would (the balance column is what was owed before).
        invoice = rentals.bill_lease(lease, self.today, user=self.user)
        if invoice:
            self.result.made(invoice)
        self.brought_forward(home, v["balance"], self.as_at(v, line), lease=lease)
        preview.update(occupant=full_name(tenant), state="Let", balance=str(v["balance"] or ZERO), rent=str(money(v["rent"])))
        return preview


# ---------------------------------------------------------------- balances only

class BalancesImport(Importer):
    kind = "balances"
    title = "Balances owed"
    estate_kinds = ("estate", "rental")
    sheet_title = "Balances"
    columns = [
        Column("reference", "Stand or reference", kind="int", required=True,
               aliases=("stand", "stand number", "reference", "ref", "property number", "unit", "unit number", "number")),
        Column("address", "Address", max_length=200, help="Only needed when two homes share a number."),
        Column("balance", "Balance owed (USD)", kind="money", required=True,
               aliases=("balance", "arrears", "amount owed", "owed", "levy owed", "rent owed", "balance usd")),
        BALANCE_DATE,
    ]
    examples = [["101", "", "45", "2025-10-31"], ["102", "", "-20", "2025-10-31"], ["103", "", "0", ""]]
    notes = [
        "For homes or properties already in Smart Estate: what each one owed before you started using it.",
        "Positive: they owe this much. Negative: they paid ahead. 0: nothing (the row is skipped).",
        "Rental portfolios: the balance goes on the current tenant's account.",
    ]

    def prepare(self, rows):
        self._seen = {}

    def row(self, line, v):
        homes = Home.objects.filter(stand__stand_number=v["reference"], status=True).select_related("stand", "resident")
        if v["address"]:
            homes = [h for h in homes if squash(h.address) == squash(v["address"])] or list(homes)
        homes = list(homes)
        if not homes:
            raise RowProblem(f"No home or property with number {v['reference']}.", "reference")
        if len(homes) > 1:
            raise RowProblem(f"Number {v['reference']} has {len(homes)} homes. Add the address to say which one.", "address")
        home = homes[0]
        if home.pk in self._seen:
            raise RowProblem(f"This home is also on row {self._seen[home.pk]}.", "reference")
        self._seen[home.pk] = line
        lease = None
        if self.estate.is_rental:
            lease = Lease.objects.filter(home=home, status=Lease.ACTIVE).select_related("tenant").first()
            if not lease and v["balance"]:
                raise RowProblem("This property has no tenant now. Start the lease first, then load the balance.", "balance")
        if not v["balance"]:
            return None
        before = Invoice.objects.filter(home=home, kind=Invoice.OPENING, void=False, **({"lease": lease} if lease else {}))
        if before.exists() or Payment.objects.filter(home=home, method=Payment.OPENING, **({"lease": lease} if lease else {})).exists():
            self.warn(line, "This home already has a balance brought forward. This adds another one.", "balance")
        self.brought_forward(home, v["balance"], self.as_at(v, line), lease=lease)
        self.result.count("balances")
        person = lease.tenant if lease else home.resident
        return {"reference": v["reference"], "address": home.address, "owner": "", "occupant": full_name(person) if person else "",
                "state": "", "balance": str(v["balance"])}


IMPORTERS = {cls.kind: cls for cls in (HomesImport, PropertiesImport, BalancesImport)}


def for_estate(estate):
    return [cls for cls in IMPORTERS.values() if estate.kind in cls.estate_kinds]
