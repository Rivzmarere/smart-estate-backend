"""Leases, monthly rent, reminders, the rent roll and owner statements."""

import calendar
import datetime
import logging
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from estates.context import current_estate
from home.models import Home
from levy.accounts import ZERO, account, allocate, fmt_usd, money
from levy.models import Invoice, Payment
from parameters.models.models_home_status import HomeStatus
from portal.models import HouseholdMember
from sms.sender import send_sms
from whatsapp.notifications import notify

from .models import Expense, Lease

logger = logging.getLogger(__name__)

ENDING_SOON = datetime.timedelta(days=60)
REMIND_BEFORE = datetime.timedelta(days=3)
REMIND_AGAIN_AFTER = datetime.timedelta(days=7)
BILL_AHEAD = datetime.timedelta(days=7)


class LeaseError(Exception):
    pass


def month_start(day):
    return day.replace(day=1)


def month_end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def next_month(day):
    return (month_start(day) + datetime.timedelta(days=32)).replace(day=1)


def full_name(person):
    return f"{person.name} {person.surname}".strip() if person else ""


def _set_home_status(home, names):
    """Use the shared 'Rented' / 'Vacant' options when the installation has them."""
    for name in names:
        found = HomeStatus.objects.filter(name__iexact=name, status=True).first()
        if found:
            home.home_status = found
            return


# ---------------------------------------------------------------- leases

def bill_lease(lease, period, user=None, amount=None):
    """The rent invoice for one month, or None when it exists or the lease does not cover that month."""
    period = month_start(period)
    if lease.status != Lease.ACTIVE or lease.start_date > month_end(period):
        return None
    if lease.end_date and lease.end_date < period:
        return None
    if Invoice.objects.filter(lease=lease, period=period, kind=Invoice.RENT, void=False).exists():
        return None
    amount = lease.rent_usd if amount is None else amount
    if amount <= 0:
        return None
    due = max(period.replace(day=lease.due_day), lease.start_date)
    return Invoice.objects.create(
        home=lease.home, lease=lease, stand_number=lease.home.stand.stand_number, address=lease.home.address,
        kind=Invoice.RENT, period=period, description=f"Rent for {period:%B %Y}", amount_usd=money(amount),
        due_date=due, created_by=user,
    )


@transaction.atomic
def start_lease(home, tenant, user=None, first_rent_usd=None, **fields):
    """
    Put a tenant in a property. The tenant becomes the home's main resident,
    so the bot, USSD and the portal work for them at once.
    first_rent_usd: rent for the month they move in (None = a full month, 0 = nothing).
    """
    if Lease.objects.filter(home=home, status=Lease.ACTIVE).exists():
        raise LeaseError("This property already has a tenant. End that lease first.")
    end = fields.get("end_date")
    if end and end < fields["start_date"]:
        raise LeaseError("The lease cannot end before it starts.")
    lease = Lease.objects.create(home=home, tenant=tenant, created_by=user, **fields)
    home.resident = tenant
    _set_home_status(home, ["Rented", "Occupied"])
    home.save()
    if lease.start_date <= month_end(timezone.localdate()):
        bill_lease(lease, lease.start_date, user=user, amount=first_rent_usd)
    return lease


@transaction.atomic
def end_lease(lease, ended_on, user=None, deposit_returned_usd=ZERO, deposit_deducted_usd=ZERO, reason=""):
    """
    The tenant moves out. Money kept from the deposit is paid into their rent
    account; rent billed for later months is cancelled.
    """
    lease = Lease.objects.select_for_update().get(pk=lease.pk)
    if lease.status != Lease.ACTIVE:
        raise LeaseError("This lease has already ended.")
    if ended_on < lease.start_date:
        raise LeaseError("The move-out date is before the lease started.")
    returned, deducted = money(deposit_returned_usd), money(deposit_deducted_usd)
    if returned + deducted > lease.deposit_paid_usd:
        raise LeaseError(f"Only {fmt_usd(lease.deposit_paid_usd)} deposit was received.")
    lease.status = Lease.ENDED
    lease.ended_on = ended_on
    lease.end_reason = reason
    lease.deposit_returned_usd, lease.deposit_deducted_usd = returned, deducted
    lease.save()
    Invoice.objects.filter(lease=lease, kind=Invoice.RENT, void=False, period__gt=month_start(ended_on)).update(
        void=True, void_reason="Lease ended"
    )
    if deducted > 0:
        payment = Payment.objects.create(
            home=lease.home, lease=lease, currency=Payment.USD, amount=deducted, amount_usd=deducted, method=Payment.DEPOSIT,
            status=Payment.PENDING, channel=Payment.OFFICE, note="Kept from the deposit", recorded_by=user,
        )
        payment.mark_paid()
    home = lease.home
    if home.resident_id == lease.tenant_id:
        home.resident = None
        _set_home_status(home, ["Vacant"])
        home.save()
        HouseholdMember.objects.filter(home=home, active=True).update(active=False)
    return lease


def lease_account(lease, today=None):
    return account(lease.home, today=today, lease=lease)


def bill_rent(period, user=None, preview=False):
    """Bill every active lease for one month. Returns (created or to create, already billed)."""
    period = month_start(period)
    leases = list(Lease.objects.filter(status=Lease.ACTIVE).select_related("home__stand"))
    billed = set(Invoice.objects.filter(kind=Invoice.RENT, period=period, void=False).values_list("lease_id", flat=True))
    due = [
        lease for lease in leases
        if lease.id not in billed and lease.start_date <= month_end(period) and not (lease.end_date and lease.end_date < period) and lease.rent_usd > 0
    ]
    if not preview:
        with transaction.atomic():
            for lease in due:
                bill_lease(lease, period, user=user)
    return len(due), len(billed)


# ---------------------------------------------------------------- reminders

def _reminder_phone(lease):
    tenant = lease.tenant
    return tenant.phone_number1 or tenant.phone_number2 or ""


def send_rent_reminders(today=None):
    """
    One message per tenant: three days before rent is due, and weekly while it is late.
    Returns the number of tenants reminded.
    """
    today = today or timezone.localdate()
    estate = current_estate()
    if not getattr(estate, "rent_reminders", False):
        return 0
    sent = 0
    for lease in Lease.objects.filter(status=Lease.ACTIVE).select_related("home", "tenant"):
        acc = lease_account(lease, today)
        unpaid = [row for row in acc["invoices"] if row["outstanding"] > 0]
        late = [row for row in unpaid if row["state"] == "overdue"]
        soon = [row for row in unpaid if today <= row["invoice"].due_date <= today + REMIND_BEFORE]
        if late:
            rows = late
            if not any(r["invoice"].last_reminder_on is None or today - r["invoice"].last_reminder_on >= REMIND_AGAIN_AFTER for r in rows):
                continue
            owed = sum((r["outstanding"] for r in rows), ZERO)
            text = f"{estate.name}: rent of {fmt_usd(owed)} for {lease.home.address} is overdue. Please pay as soon as you can."
        elif soon:
            rows = [r for r in soon if r["invoice"].last_reminder_on is None]
            if not rows:
                continue
            owed = sum((r["outstanding"] for r in rows), ZERO)
            due = min(r["invoice"].due_date for r in rows)
            text = f"{estate.name}: rent of {fmt_usd(owed)} for {lease.home.address} is due on {due:%d %b}."
        else:
            continue
        text += f" Pay with EcoCash at {settings.RESIDENT_PORTAL_URL}/?estate={estate.slug}"
        phone = _reminder_phone(lease)
        if not phone:
            continue
        try:
            if not notify(phone, text):
                send_sms(phone, text)
        except Exception:
            logger.exception("Could not send a rent reminder for lease %s", lease.pk)
            continue
        Invoice.objects.filter(pk__in=[r["invoice"].pk for r in rows]).update(last_reminder_on=today)
        sent += 1
    return sent


# ---------------------------------------------------------------- rent roll

def _period_bounds(start, end):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.datetime.combine(start, datetime.time.min), tz),
        timezone.make_aware(datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min), tz),
    )


def collected_between(start, end):
    """{home_id: USD received} for payments made from start to end, inclusive."""
    begin, finish = _period_bounds(start, end)
    return dict(
        Payment.objects.filter(status=Payment.PAID, paid_at__gte=begin, paid_at__lt=finish)
        .values_list("home_id").annotate(total=Sum("amount_usd")).values_list("home_id", "total")
    )


def lease_state(lease, today):
    if lease is None:
        return "vacant"
    if lease.end_date and lease.end_date < today:
        return "expired"
    if lease.end_date and lease.end_date <= today + ENDING_SOON:
        return "ending"
    return "let"


def rent_roll(today=None):
    """Every property with its tenant, rent and what is owed. Returns (rows, totals)."""
    today = today or timezone.localdate()
    leases = {l.home_id: l for l in Lease.objects.filter(status=Lease.ACTIVE).select_related("tenant")}
    invoices = defaultdict(list)
    for invoice in Invoice.objects.filter(void=False, lease__status=Lease.ACTIVE).only("id", "lease_id", "amount_usd", "due_date"):
        invoices[invoice.lease_id].append(invoice)
    paid = dict(
        Payment.objects.filter(status=Payment.PAID, lease__status=Lease.ACTIVE)
        .values_list("lease_id").annotate(total=Sum("amount_usd"), last=Max("paid_at")).values_list("lease_id", "total")
    )
    last_paid = dict(
        Payment.objects.filter(status=Payment.PAID, lease__status=Lease.ACTIVE)
        .values_list("lease_id").annotate(last=Max("paid_at")).values_list("lease_id", "last")
    )
    month = collected_between(month_start(today), month_end(today))

    rows = []
    for home in Home.objects.filter(status=True).select_related("stand", "owner").order_by("stand__stand_number", "id"):
        lease = leases.get(home.id)
        balance = arrears = ZERO
        if lease:
            lease_invoices = invoices.get(lease.id, [])
            lease_paid = paid.get(lease.id) or ZERO
            _, arrears, _ = allocate(lease_invoices, lease_paid, today)
            balance = money(sum((i.amount_usd for i in lease_invoices), ZERO) - lease_paid)
        rows.append({
            "home_id": home.id,
            "reference": home.stand.stand_number,
            "address": home.address,
            "owner_id": home.owner_id,
            "owner": full_name(home.owner),
            "state": lease_state(lease, today),
            "lease_id": lease.id if lease else None,
            "tenant": full_name(lease.tenant) if lease else "",
            "tenant_phone": (lease.tenant.phone_number1 or "") if lease else "",
            "rent_usd": lease.rent_usd if lease else None,
            "due_day": lease.due_day if lease else None,
            "lease_start": lease.start_date if lease else None,
            "lease_end": lease.end_date if lease else None,
            "deposit_held_usd": lease.deposit_held_usd if lease else None,
            "balance": balance,
            "arrears": arrears,
            "last_paid_at": last_paid.get(lease.id) if lease else None,
        })
    let = [r for r in rows if r["lease_id"]]
    totals = {
        "properties": len(rows),
        "let": len(let),
        "vacant": len(rows) - len(let),
        "monthly_rent": sum((r["rent_usd"] for r in let), ZERO),
        "balance": sum((r["balance"] for r in let if r["balance"] > 0), ZERO),
        "arrears": sum((r["arrears"] for r in let), ZERO),
        "tenants_in_arrears": sum(1 for r in let if r["arrears"] > 0),
        "collected_this_month": sum(month.values(), ZERO),
        "leases_ending": sum(1 for r in let if r["state"] in ("ending", "expired")),
    }
    return rows, totals


# ---------------------------------------------------------------- statements

def statement(start, end, owner=None):
    """
    Money in and out per property from start to end (cash basis):
    rent received, expenses, the agent's fee, and what is left for the owner.
    """
    estate = current_estate()
    fee_rate = Decimal(getattr(estate, "management_fee_percent", 0) or 0) / Decimal(100)
    income = collected_between(start, end)
    spent = defaultdict(list)
    for expense in Expense.objects.filter(date__gte=start, date__lte=end).order_by("date", "id"):
        spent[expense.home_id].append(expense)
    homes = Home.objects.select_related("stand", "owner", "resident").order_by("stand__stand_number", "id")
    if owner is not None:
        homes = homes.filter(owner=owner)

    def expense_row(e):
        return {"id": e.id, "date": e.date, "category": e.get_category_display(), "description": e.description,
                "paid_to": e.paid_to, "amount_usd": e.amount_usd}

    rows = []
    for home in homes:
        received = money(income.get(home.id) or ZERO)
        costs = spent.get(home.id, [])
        if not home.status and not received and not costs:
            continue
        expenses = money(sum((e.amount_usd for e in costs), ZERO))
        fee = money(received * fee_rate)
        rows.append({
            "home_id": home.id, "reference": home.stand.stand_number, "address": home.address,
            "owner": full_name(home.owner), "tenant": full_name(home.resident),
            "income": received, "expenses": expenses, "fee": fee, "net": money(received - expenses - fee),
            "expense_items": [expense_row(e) for e in costs],
        })
    general = [] if owner is not None else [expense_row(e) for e in spent.get(None, [])]
    general_total = money(sum((e["amount_usd"] for e in general), ZERO))
    totals = {
        "income": sum((r["income"] for r in rows), ZERO),
        "expenses": sum((r["expenses"] for r in rows), ZERO) + general_total,
        "fee": sum((r["fee"] for r in rows), ZERO),
    }
    totals["net"] = money(totals["income"] - totals["expenses"] - totals["fee"])
    return {
        "from": start, "to": end, "fee_percent": getattr(estate, "management_fee_percent", 0),
        "properties": rows, "general_expenses": general, "totals": totals,
    }
