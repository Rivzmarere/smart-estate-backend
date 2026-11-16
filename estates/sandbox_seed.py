"""
Sample data for sandbox estates: a believable Harare estate with homes,
owners, tenants, family members, visitors, repairs, levies, notices and more.

Demo phone numbers follow the stand number so testers can guess them:
    main resident of stand 1NN   0771 000 1NN
    owner of stand 1NN           0772 000 1NN   (some owners have two homes)
    household member             0773 000 1NN
Nothing is ever sent to these numbers: sandbox messages stay in the Outbox.
"""

import datetime
import random
import secrets
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from assist.models import Conversation, ConversationMessage, EmergencyAlert
from authentication.models import User
from complaint.models import Complain
from home.models import Home
from levy.models import ExchangeRate, Invoice, Payment
from notice.models import Notice
from owner.models import Owner
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.models.models_gender import Gender
from parameters.models.models_home_status import HomeStatus
from parameters.models.models_nationality import Nationality
from parameters.models.models_provider_category import ProviderCategory
from parameters.models.models_stand_status import StandStatus
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from portal.models import HouseholdMember, HouseholdRequest
from provider.models import Provider
from resident.models import Resident
from smartEstateBackend.permissions import ROLE_ADMIN, ROLE_GUARD
from stand.models import Stand
from visit.models import Visit
from visit.utilities import random_numbers
from whitelist.models import WhiteList, WhiteListGuest

from .context import use_estate
from .models import Estate, SandboxMessage

STREETS = ["Acacia Drive", "Jacaranda Road", "Msasa Close", "Mopane Way", "Flamboyant Lane"]
PEOPLE = [
    ("Rudo", "Moyo", "F"), ("Tendai", "Ncube", "M"), ("Farai", "Dube", "M"), ("Chipo", "Banda", "F"),
    ("Tatenda", "Sibanda", "M"), ("Nyasha", "Mlambo", "F"), ("Tafadzwa", "Chikore", "M"), ("Kudzai", "Mutasa", "F"),
    ("Tinashe", "Gumbo", "M"), ("Rumbidzai", "Zvobgo", "F"), ("Simbarashe", "Chari", "M"), ("Fadzai", "Mhlanga", "F"),
    ("Blessing", "Mpofu", "M"), ("Ruvimbo", "Chinoda", "F"), ("Panashe", "Nyathi", "M"), ("Vimbai", "Hove", "F"),
    ("Tapiwa", "Shumba", "M"), ("Memory", "Ndlovu", "F"), ("Gift", "Mukwena", "M"), ("Shamiso", "Marufu", "F"),
]
LANDLORDS = [("Tawanda", "Makoni", "M"), ("Precious", "Chiwenga", "F"), ("Clever", "Mupfumi", "M"), ("Loveness", "Sithole", "F")]
VISITORS = ["Tariro Gwenzi", "Munyaradzi Phiri", "Kelvin Zulu", "Netsai Chirwa", "Brian Mazvita", "Patience Dhliwayo",
            "Takunda Muzenda", "Grace Nyoni", "Ashley Mutero", "Ronald Tembo", "DHL Courier", "ZESA Technician"]
PROVIDERS = [
    ("Plumbing", "Joseph", "Mandaza", "Avondale, Harare"), ("Plumbing", "Lovemore", "Chigumba", "Mabelreign, Harare"),
    ("Electrical", "Edmore", "Kativhu", "Belvedere, Harare"), ("Electrical", "Patrick", "Mushonga", "Msasa, Harare"),
    ("Gardening", "Peter", "Chidzikwe", "Greendale, Harare"), ("Domestic help", "Mavis", "Tshuma", "Mbare, Harare"),
    ("Building", "Stanley", "Moyo", "Chitungwiza"), ("Security", "Guardsafe", "Services", "Eastlea, Harare"),
]
STAND_COUNT = 20


def resident_phone(stand):
    return f"0771000{stand}"


def owner_phone(stand):
    return f"0772000{stand}"


def member_phone(stand):
    return f"0773000{stand}"


def param(model, wanted):
    """Reuse the shared reference lists; only add names that are missing, never rename."""
    found = {}
    for name in wanted:
        obj = model.objects.filter(name__iexact=name).first() or model.objects.create(name=name)
        found[name] = obj
    return found


def _id_number(rng):
    return f"{rng.randint(10, 85)}-{rng.randint(100000, 999999)}{rng.choice('ABCDEFGHJKLMNPQRSTVWXYZ')}{rng.randint(10, 99)}"


def _at(days_ago, hour, minute=0):
    day = timezone.localdate() - datetime.timedelta(days=days_ago)
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)))


def password():
    return f"Demo-{secrets.token_urlsafe(6)}"


def create_tester(estate, role, label=""):
    """A login for someone testing the sandbox. Returns (username, password)."""
    base = f"{estate.slug}-{role.lower()}" + (f"-{label}" if label else "")
    username, n = base[:45], 2
    while User.objects.filter(username=username).exists():
        username, n = f"{base[:42]}-{n}", n + 1
    secret = password()
    User.objects.create_user(username=username, password=secret, role=role, estate=estate,
                             first_name=label.title() if label else ("Gate" if role == ROLE_GUARD else "Demo"),
                             last_name="Guard" if role == ROLE_GUARD else "Admin")
    return username, secret


@transaction.atomic
def seed(estate, staff=None):
    """Fill a (sandbox) estate with sample data. `staff` is the admin user recorded as creator."""
    rng = random.Random(estate.pk)
    gender = param(Gender, ["Female", "Male"])
    nationality = param(Nationality, ["Zimbabwean", "South African", "Zambian"])
    stand_status = param(StandStatus, ["Occupied", "Vacant"])
    home_status = param(HomeStatus, ["Owner occupied", "Rented", "Vacant"])
    visit_status = param(VisitStatus, ["Expected", "Inside", "Departed"])
    transport = param(TransportType, ["Walking", "Driving", "Taxi"])
    complaint_status = param(ComplaintStatus, ["Pending", "In progress", "Resolved"])
    category = param(ComplaintCategory, ["Water & plumbing", "Electricity", "Roads & lights", "Security", "Refuse collection"])
    provider_category = param(ProviderCategory, ["Plumbing", "Electrical", "Gardening", "Domestic help", "Building", "Security"])
    sex = {"F": gender["Female"], "M": gender["Male"]}
    zim = nationality["Zimbabwean"]

    with use_estate(estate):
        estate.office_phone = estate.office_phone or "0242 000 101"
        estate.office_hours = estate.office_hours or "Mon-Fri 08:00-16:30, Sat 08:00-12:00"
        estate.emergency_phones = estate.emergency_phones or "0771 999 001, 0771 999 002"
        estate.address = estate.address or "Off Harare Drive, Harare"
        estate.save()
        staff = staff or User.objects.filter(estate=estate, role=ROLE_ADMIN).first()

        landlords = []
        for n, (first, last, s) in enumerate(LANDLORDS):
            landlords.append(Owner.objects.create(
                name=first, surname=last, id_number=_id_number(rng), date_of_birth=datetime.date(1965 + n * 4, 3 + n, 12),
                gender=sex[s], nationality=zim, phone_number1=owner_phone(190 + n), phone_number2="",
                email=f"{first.lower()}.{last.lower()}@example.co.zw", authorized_by=staff,
            ))

        homes = []
        for i in range(STAND_COUNT):
            number = 101 + i
            first, last, s = PEOPLE[i]
            vacant = number in (118, 120)
            rented = number % 4 == 3  # some homes are let by a landlord
            stand = Stand.objects.create(stand_number=number, stand_status=stand_status["Vacant" if vacant else "Occupied"], authorized_by=staff)
            if rented:
                owner = landlords[i % len(landlords)]
            else:
                owner = Owner.objects.create(
                    name=first, surname=last, id_number=_id_number(rng), date_of_birth=datetime.date(1960 + i, 1 + i % 12, 5 + i),
                    gender=sex[s], nationality=zim, phone_number1=owner_phone(number), phone_number2="",
                    email=f"{first.lower()}@example.co.zw", authorized_by=staff,
                )
            resident = None
            if not vacant:
                resident = Resident.objects.create(
                    name=first, surname=last, id_number=_id_number(rng), date_of_birth=datetime.date(1970 + i, 1 + i % 12, 3 + i),
                    gender=sex[s], nationality=zim, phone_number1=resident_phone(number), authorized_by=staff,
                )
            home = Home.objects.create(
                owner=owner, stand=stand, resident=resident, authorized_by=staff,
                address=f"{number} {STREETS[i % len(STREETS)]}",
                home_status=home_status["Vacant" if vacant else "Rented" if rented else "Owner occupied"],
            )
            homes.append(home)

        occupied = [h for h in homes if h.resident_id]

        # Household members: family and domestic workers.
        for home, (name, relationship) in zip(occupied[:6], [("Tanaka", "family"), ("Mai Tendai", "worker"), ("Kuda", "family"),
                                                             ("Sekuru Josiah", "family"), ("Thandi", "worker"), ("Nokutenda", "family")]):
            HouseholdMember.objects.create(home=home, name=name, surname=home.resident.surname if relationship == "family" else "",
                                           phone="+263" + member_phone(home.stand.stand_number)[1:], relationship=relationship)
        HouseholdRequest.objects.create(
            home=occupied[0], kind=HouseholdRequest.ADD_MEMBER, requested_by_phone="+263" + resident_phone(occupied[0].stand.stand_number)[1:],
            requested_by_role="resident",
            details={"name": "Ropafadzo", "surname": occupied[0].resident.surname, "phone": "+263774000101", "relationship": "family", "can_book_visitors": True},
        )

        # Visitors: today (expected, inside, left) and the past fortnight.
        def visit(home, name, days_ago, hour, arrived=None, left=None, code_transport="Walking", reg=None, cancelled=False):
            v = Visit.objects.create(
                stand_number=home.stand.stand_number, home=home.address, visit_code=random_numbers(),
                resident_phone_number=home.resident.phone_number1, visitor_name=name,
                visitor_national_id=_id_number(rng) if arrived else "", visitor_vehicle_reg_number=reg,
                transport_type=transport[code_transport], visit_status=visit_status["Departed" if left else "Inside" if arrived else "Expected"],
                authorized_by=None, status=not cancelled,
            )
            Visit.objects.filter(pk=v.pk).update(
                date_created=_at(days_ago, hour), date_arrived=_at(days_ago, *arrived) if arrived else None,
                date_depature=_at(days_ago, *left) if left else None,
            )

        today_now = timezone.localtime().hour
        for n, home in enumerate(occupied[:4]):
            visit(home, VISITORS[n], 0, max(6, today_now - 1), code_transport="Driving" if n % 2 else "Walking", reg="AEZ 4521" if n % 2 else None)
        for n, home in enumerate(occupied[4:7]):
            visit(home, VISITORS[4 + n], 0, 7, arrived=(7, 30 + n * 5), code_transport="Driving", reg=f"AFB {2300 + n}")
        for days_ago in range(1, 14):
            for n in range(rng.randint(2, 5)):
                home = rng.choice(occupied)
                arrive = (rng.randint(8, 17), rng.choice([0, 15, 30, 45]))
                visit(home, rng.choice(VISITORS), days_ago, arrive[0] - 1 if arrive[0] > 7 else 7, arrived=arrive,
                      left=(min(arrive[0] + rng.randint(1, 4), 22), rng.choice([0, 20, 40])), code_transport=rng.choice(list(transport)))
        visit(occupied[7], "Cancelled Visitor", 2, 9, cancelled=True)

        # Whitelist: regular visitors (domestic workers, gardener).
        for home, name in [(occupied[1], "Mai Tendai"), (occupied[3], "Peter Gardener")]:
            guest = WhiteListGuest.objects.create(
                stand_number=home.stand.stand_number, home=home.address, visit_code=random_numbers(),
                resident_phone_number=home.resident.phone_number1, visitor_name=name, visitor_national_id=_id_number(rng), authorized_by=staff,
            )
            entry = WhiteList.objects.create(white_list_guest=guest, transport_type=transport["Walking"], visit_status=visit_status["Departed"], authorized_by=staff)
            WhiteList.all_estates.filter(pk=entry.pk).update(date_arrived=_at(1, 7, 10), date_depature=_at(1, 16, 30))

        # Repairs.
        repairs = [
            (0, "Water & plumbing", "Burst pipe outside the gate, water running since morning.", "In progress", 1),
            (2, "Electricity", "Street light on the corner has been off for a week.", "Pending", 3),
            (5, "Roads & lights", "Large pothole by the main entrance.", "Pending", 6),
            (8, "Security", "Gap in the boundary wall behind the house.", "In progress", 2),
            (10, "Refuse collection", "Bins not collected on Tuesday.", "Resolved", 9),
            (12, "Water & plumbing", "Low water pressure in the mornings.", "Resolved", 12),
        ]
        for index, cat, text, status, days_ago in repairs:
            home = occupied[index]
            c = Complain.objects.create(
                stand_number=home.stand.stand_number, home=home.address, complain_code=random_numbers(),
                resident_phone_number=home.resident.phone_number1, description=text, complaint_category=category[cat],
                compalint_status=complaint_status[status], assigned_to=staff if status != "Pending" else None,
            )
            Complain.all_estates.filter(pk=c.pk).update(date_created=_at(days_ago, 10))

        # Service providers.
        for cat, first, last, area in PROVIDERS:
            Provider.objects.create(name=first, surname=last, address=area, id_number=_id_number(rng),
                                    phone_number1=f"0778{rng.randint(100000, 999999)}", phone_number2=None,
                                    provider_category=provider_category[cat], authorized_by=staff)

        # Notices.
        notices = [
            ("Water interruption on Tuesday", "ZINWA maintenance on the main line from 08:00 to 14:00. Please store water on Monday night.", "water", True, 1),
            ("Annual General Meeting", "The AGM is on Saturday the 6th at 10:00 in the clubhouse. Agenda: levy budget, security contract, road repairs.", "meeting", False, 3),
            ("Levies due by the 7th", "Monthly levies of USD 45 are due by the 7th. Pay on WhatsApp with EcoCash, or at the office.", "levy", False, 5),
            ("New security guards", "Guardsafe Services starts on the 1st. Please book visitors so the gate knows who to expect.", "security", False, 9),
        ]
        if staff:
            for title, body, cat, pinned, days_ago in notices:
                n = Notice.objects.create(title=title, body=body, category=cat, pinned=pinned, created_by=staff, publish_at=_at(days_ago, 9))
                Notice.all_estates.filter(pk=n.pk).update(publish_at=_at(days_ago, 9))

        # Levies: three months at USD 45; most paid, a few behind.
        ExchangeRate.objects.create(effective_from=timezone.localdate() - datetime.timedelta(days=30), zig_per_usd=Decimal("26.80"), note="RBZ interbank")
        first_of_month = timezone.localdate().replace(day=1)
        months = []
        for back in (2, 1, 0):
            m = first_of_month
            for _ in range(back):
                m = (m - datetime.timedelta(days=1)).replace(day=1)
            months.append(m)
        behind = {occupied[2].pk: 2, occupied[6].pk: 1, occupied[9].pk: 3}
        for home in occupied:
            for m in months:
                Invoice.objects.create(home=home, stand_number=home.stand.stand_number, address=home.address, kind=Invoice.LEVY,
                                       period=m, description=f"Levy for {m:%B %Y}", amount_usd=Decimal("45.00"),
                                       due_date=m.replace(day=7), created_by=staff)
            paid_months = len(months) - behind.get(home.pk, 0)
            for k in range(paid_months):
                method = rng.choice([Payment.ECOCASH, Payment.ECOCASH, Payment.CASH, Payment.BANK])
                p = Payment.objects.create(home=home, amount=Decimal("45.00"), amount_usd=Decimal("45.00"), method=method,
                                           status=Payment.PENDING, channel=Payment.WHATSAPP if method == Payment.ECOCASH else Payment.OFFICE,
                                           phone=home.resident.phone_number1 if method == Payment.ECOCASH else "", recorded_by=None if method == Payment.ECOCASH else staff)
                p.mark_paid(when=_at(max(0, (timezone.localdate() - months[k]).days - 3), 11))

        # An emergency that was dealt with, and a chat with the office.
        alert = EmergencyAlert.objects.create(home=occupied[5], stand_number=occupied[5].stand.stand_number, address=occupied[5].address,
                                              resident_name=f"{occupied[5].resident.name} {occupied[5].resident.surname}",
                                              wa_id="263" + resident_phone(occupied[5].stand.stand_number)[1:], kind=EmergencyAlert.SECURITY,
                                              details="Someone trying the back gate.", status=EmergencyAlert.RESOLVED,
                                              acknowledged_by=staff, acknowledged_at=_at(4, 22, 7), resolved_by=staff, resolved_at=_at(4, 22, 40))
        EmergencyAlert.all_estates.filter(pk=alert.pk).update(created_at=_at(4, 22, 5))
        home = occupied[3]
        convo = Conversation.objects.create(home=home, stand_number=home.stand.stand_number, address=home.address,
                                            resident_name=f"{home.resident.name} {home.resident.surname}",
                                            wa_id="263" + resident_phone(home.stand.stand_number)[1:], unread=1, last_message_at=timezone.now(),
                                            channel=Conversation.WHATSAPP)
        ConversationMessage.objects.create(conversation=convo, direction="in", text="Hello, can I get a second gate remote for my daughter?")
    return {"homes": len(homes), "occupied": len(occupied)}


ESTATE_MODELS_IN_DELETE_ORDER = [
    "estates.SandboxMessage", "assist.ConversationMessage", "assist.Conversation", "assist.EmergencyAlert",
    "portal.HouseholdRequest", "portal.HouseholdMember", "gatepass.WalkInRequest", "levy.Payment", "levy.Invoice",
    "levy.ExchangeRate", "complaint.ComplaintPhoto", "complaint.Complain", "whitelist.WhiteList", "whitelist.WhiteListGuest",
    "visit.Visit", "notice.Notice", "provider.Provider", "home.Home", "stand.Stand", "resident.Resident", "owner.Owner",
]


@transaction.atomic
def wipe(estate):
    """Delete a sandbox estate's data (not its staff accounts)."""
    from django.apps import apps

    if not estate.sandbox:
        raise ValueError("Only sandbox estates can be wiped.")
    for label in ESTATE_MODELS_IN_DELETE_ORDER:
        apps.get_model(label).all_estates.filter(estate=estate).delete()


def create_sandbox(name, slug=None):
    """A new sandbox estate with sample data, an admin and a guard. Returns (estate, [(role, username, password)])."""
    estate = Estate.objects.create(name=name, slug=slug or "", sandbox=True)
    admin = create_tester(estate, ROLE_ADMIN)
    guard = create_tester(estate, ROLE_GUARD)
    seed(estate, staff=User.objects.get(username=admin[0]))
    return estate, [("Admin", *admin), ("Guard", *guard)]


def reset(estate):
    wipe(estate)
    return seed(estate)


def demo_people(estate):
    """Who testers can be on the portal, WhatsApp simulator and USSD."""
    rows = []
    with use_estate(estate):
        for home in Home.objects.filter(status=True).select_related("stand", "resident", "owner").order_by("stand__stand_number"):
            if home.resident:
                rows.append({"stand": home.stand.stand_number, "address": home.address, "role": "Main resident",
                             "name": f"{home.resident.name} {home.resident.surname}", "phone": home.resident.phone_number1})
            rows.append({"stand": home.stand.stand_number, "address": home.address, "role": "Owner",
                         "name": f"{home.owner.name} {home.owner.surname}", "phone": home.owner.phone_number1})
            for m in HouseholdMember.objects.filter(home=home, active=True):
                rows.append({"stand": home.stand.stand_number, "address": home.address, "role": f"Member ({m.get_relationship_display().lower()})",
                             "name": m.full_name, "phone": "0" + m.phone[4:]})
    return rows


__all__ = ["seed", "wipe", "reset", "create_sandbox", "create_tester", "demo_people", "SandboxMessage"]
