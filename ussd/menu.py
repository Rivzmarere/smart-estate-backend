"""
USSD menus (*xxx#) for residents on any phone.

The gateway sends every answer given so far in one string, e.g. "1*Chipo Banda*0*2".
The menu replays those answers from the start each time, so nothing has to be
remembered between requests. Only the last step of a path does anything
(book, pay, report, alert), and it always ends the session.

Screens stay under 182 characters, the USSD limit.
"""

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from assist import services as assist
from assist.models import EmergencyAlert
from complaint.models import Complain
from estates.context import use_estate
from levy import paynow
from levy.accounts import account
from levy.services import pending_payment, start_payment
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from portal.access import homes_for_phone
from sms.sender import send_sms, zimbabwe_mobile
from visit.messaging import send_code_to_visitor
from visit.models import Visit
from visit.utilities import random_numbers
from whatsapp.bot import initial_status, new_visit_code

MAX_CHARS = 182
EMERGENCY_KINDS = [(EmergencyAlert.SECURITY, "Security/intruder"), (EmergencyAlert.MEDICAL, "Medical"),
                   (EmergencyAlert.FIRE, "Fire"), (EmergencyAlert.OTHER, "Other")]


class End(Exception):
    def __init__(self, message):
        self.message = message


def cut(text, limit=MAX_CHARS):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def usd(value):
    return f"USD {Decimal(value):,.2f}"


def local(phone):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return "0" + digits[3:] if digits.startswith("263") else digits


def menu(title, options):
    return "\n".join([title] + [f"{n}. {label}" for n, label in enumerate(options, start=1)])


def pick(answer, options):
    """The chosen option for a numbered answer, or None."""
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return options[int(answer) - 1]
    return None


class Session:
    """Walks the answers in order; each step either consumes the next answer or asks for it."""

    def __init__(self, phone, answers):
        self.phone = phone
        self.answers = answers
        self.position = 0

    def next(self, prompt):
        """The next answer, or raise Ask(prompt) when the user has not answered yet."""
        if self.position >= len(self.answers):
            raise Ask(prompt)
        answer = self.answers[self.position].strip()
        self.position += 1
        return answer


class Ask(Exception):
    def __init__(self, prompt):
        self.prompt = prompt


def handle(phone, text):
    """Returns (keep_open, message)."""
    phone = zimbabwe_mobile(phone)
    answers = [a for a in (text or "").split("*")] if text else []
    if not phone:
        return False, "Sorry, this service is for Zimbabwean mobile numbers."
    homes = homes_for_phone(phone, across_estates=True)
    if not homes:
        return False, "This number is not registered with an estate on Smart Estate. Please ask your estate office to add it."
    session = Session(phone, answers)
    try:
        access = homes[0]
        if len(homes) > 1:
            options = [f"{a.home.address[:28]} ({a.home.estate.name[:20]})" for a in homes[:5]]
            access = pick(session.next(menu("Choose your home:", options)), homes[:5])
            if access is None:
                raise End("Invalid choice. Please dial again.")
        with use_estate(access.home.estate):
            main_menu(session, access)
        raise End("Goodbye.")
    except Ask as ask:
        return True, cut(ask.prompt)
    except End as end:
        return False, cut(end.message)


def main_menu(session, access):
    home = access.home
    items = []
    if access.can("visitors"):
        items += [("Book a visitor", book_visitor), ("My visitors", my_visitors)]
    if access.can("levy"):
        items.append(("Levy balance / pay", levy))
    items += [("Report a fault", report_fault), ("Emergency", emergency)]
    choice = pick(session.next(menu(cut(home.estate.name, 40), [label for label, _ in items])), items)
    if choice is None:
        raise End("Invalid choice. Please dial again.")
    choice[1](session, access)


# ---------------------------------------------------------------- visitors

def book_visitor(session, access):
    home = access.home
    name = " ".join(session.next("Visitor's full name:").split())
    if len(name) < 2:
        raise End("Please dial again and enter the visitor's name.")
    raw_phone = session.next("Visitor's mobile number for the SMS code (or 0 to skip):")
    visitor_phone = None
    if raw_phone not in ("", "0"):
        visitor_phone = zimbabwe_mobile(raw_phone)
        if not visitor_phone:
            raise End("That is not a Zimbabwean mobile number. Please dial again.")
    transports = list(TransportType.objects.filter(status=True).order_by("id")[:5])
    transport = transports[0] if len(transports) == 1 else None
    if transport is None:
        transport = pick(session.next(menu("How are they coming?", [t.name for t in transports])), transports)
        if transport is None:
            raise End("Invalid choice. Please dial again.")
    confirm = session.next(f"Book {name[:40]} ({transport.name})?\n1. Yes\n2. No")
    if confirm != "1":
        raise End("Booking cancelled.")
    status = initial_status(VisitStatus, ["Coming", "Expected", "Pending"])
    if status is None:
        raise End("Bookings are not set up yet. Please contact the estate office.")
    visit = Visit.objects.create(
        stand_number=home.stand.stand_number, home=home.address, visit_code=new_visit_code(),
        resident_phone_number=local(session.phone), visitor_name=name[:60], visitor_phone_number=visitor_phone,
        transport_type=transport, visit_status=status,
    )
    sent = send_code_to_visitor(visit, host_name=home.resident.name if home.resident else "")
    send_sms(session.phone, f"{home.estate.name}: {visit.visitor_name} is booked. Gate code {visit.visit_code}.")
    tail = "We sent it to your visitor by SMS." if sent else "We sent it to you by SMS; pass it on."
    raise End(f"Booked. Gate code: {visit.visit_code}. {tail}")


def my_visitors(session, access):
    home = access.home
    visits = Visit.objects.filter(stand_number=home.stand.stand_number, status=True, date_depature__isnull=True).order_by("-date_created")[:4]
    if not visits:
        raise End("You have no visitors booked.")
    lines = [f"{v.visitor_name[:16]} {v.visit_code} {'IN' if v.date_arrived else 'due'}" for v in visits]
    raise End("Your visitors:\n" + "\n".join(lines))


# ---------------------------------------------------------------- levy

def levy(session, access):
    home = access.home
    acc = account(home)
    balance = acc["balance"]
    summary = f"Balance {usd(balance)}" + (f"\nOverdue {usd(acc['arrears'])}" if acc["arrears"] > 0 else "")
    if balance <= 0:
        raise End("Your levy account is up to date. Thank you!")
    method = paynow.method_for_phone(session.phone)
    if paynow.Payment.USD not in paynow.available_currencies(home.estate) or not method:
        raise End(summary + "\nTo pay, contact the estate office.")
    if pending_payment(home):
        raise End(summary + "\nA payment request is already waiting on your phone.")
    choice = session.next(summary + "\n1. Pay all\n2. Pay another amount")
    if choice == "1":
        amount = balance
    elif choice == "2":
        try:
            amount = Decimal(session.next("Amount in USD:").replace(",", "").replace("$", "")).quantize(Decimal("0.01"))
        except InvalidOperation:
            raise End("That is not an amount. Please dial again.")
        if not Decimal("1") <= amount <= Decimal("10000"):
            raise End("Enter an amount between 1 and 10,000. Please dial again.")
    else:
        raise End("Invalid choice. Please dial again.")
    wallet = "EcoCash" if method == paynow.Payment.ECOCASH else "OneMoney"
    if session.next(f"Pay {usd(amount)} from {local(session.phone)} ({wallet})?\n1. Yes\n2. No") != "1":
        raise End("Payment cancelled.")
    try:
        start_payment(home, amount, paynow.Payment.USD, local(session.phone), wa_id=session.phone)
    except paynow.PaynowError as exc:
        raise End(f"The payment could not be started: {exc}")
    raise End(f"Approve the {wallet} prompt for {usd(amount)} with your PIN. Your receipt comes by SMS.")


# ---------------------------------------------------------------- repairs

def report_fault(session, access):
    home = access.home
    categories = list(ComplaintCategory.objects.filter(status=True).order_by("name")[:6])
    category = categories[0] if len(categories) == 1 else pick(session.next(menu("What kind of problem?", [c.name for c in categories])), categories)
    if category is None:
        raise End("Invalid choice. Please dial again.")
    description = session.next("Describe the problem and where it is:").strip()
    if len(description) < 3:
        raise End("Please dial again and describe the problem.")
    status = initial_status(ComplaintStatus, ["Pending", "Open", "New"])
    complaint = Complain.objects.create(
        stand_number=home.stand.stand_number, home=home.address, complain_code=random_numbers(),
        resident_phone_number=local(session.phone), description=description[:1000], complaint_category=category,
        compalint_status=status,
    )
    raise End(f"Thank you. Reported with reference {complaint.complain_code}. The estate office will follow up.")


# ---------------------------------------------------------------- emergency

def emergency(session, access):
    kind = pick(session.next(menu("EMERGENCY - alert estate security:", [label for _, label in EMERGENCY_KINDS])), EMERGENCY_KINDS)
    if kind is None:
        raise End("Invalid choice. Call 995 (police), 994 (ambulance) or 993 (fire).")
    alert, created = assist.raise_emergency(access.home, session.phone, kind[0])
    when = timezone.localtime(alert.created_at).strftime("%H:%M")
    first = f"Alert sent to estate security at {when}." if created else f"Security already has your alert from {when}."
    raise End(f"{first} If a life is in danger also call: Police 995, Ambulance 994, Fire 993.")
