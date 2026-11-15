"""
Smart Estate WhatsApp bot: menu-driven conversations for residents.

v1 (pilot): book a visitor, see / cancel my visitors, report a repair.
The bot identifies the resident by their WhatsApp number, which Meta has
already verified, and only serves numbers registered on a home.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from complaint.models import Complain
from home.models import Home
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from resident.models import Resident
from visit.models import Visit
from sms.sender import zimbabwe_mobile
from visit.messaging import send_code_to_visitor
from visit.utilities import phone_variants, random_numbers

from . import client
from .models import WhatsAppSession

MENU = "menu"
BOOK_NAME = "book_name"
BOOK_VISITOR_PHONE = "book_visitor_phone"
BOOK_TRANSPORT = "book_transport"
BOOK_VEHICLE = "book_vehicle"
BOOK_CONFIRM = "book_confirm"
REPAIR_CATEGORY = "repair_category"
REPAIR_DESCRIPTION = "repair_description"

# A half-finished conversation older than this starts again from the menu.
SESSION_TIMEOUT = timedelta(minutes=30)

RESET_WORDS = {"hi", "hello", "menu", "start", "0", "home", "cancel", "stop", "mhoro", "sawubona"}
SKIP_WORDS = {"skip", "no", "none", "-"}

MAX_NAME_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 1000


# ---------------------------------------------------------------- lookups

def find_home(wa_id):
    """The active home whose resident owns this WhatsApp number, or None."""
    variants = phone_variants(wa_id)
    if not variants:
        return None
    phone_match = Q()
    for field in ("phone_number1", "phone_number2", "phone_number3", "phone_number4"):
        phone_match |= Q(**{f"{field}__in": variants})
    residents = Resident.objects.filter(phone_match, status=True)
    return (
        Home.objects.filter(resident__in=residents, status=True)
        .select_related("resident", "stand")
        .order_by("id")
        .first()
    )


def local_phone(wa_id):
    """263772111111 -> 0772111111 (the format the gate staff type)."""
    digits = "".join(ch for ch in str(wa_id) if ch.isdigit())
    return "0" + digits[3:] if digits.startswith("263") else digits


def initial_status(model, preferred_names):
    """The status new records start in, matched by name, else the first one."""
    for name in preferred_names:
        found = model.objects.filter(name__iexact=name, status=True).first()
        if found:
            return found
    return model.objects.filter(status=True).order_by("id").first()


def new_visit_code():
    for _ in range(10):
        code = random_numbers()
        if not Visit.objects.filter(visit_code=code, status=True).exists():
            return code
    return random_numbers()


# ---------------------------------------------------------------- entry point

def handle_message(wa_id, message):
    """Process one inbound WhatsApp message object from the webhook."""
    session, _ = WhatsAppSession.objects.get_or_create(wa_id=wa_id)
    now = timezone.now()
    if session.state != MENU and session.updated_at and now - session.updated_at > SESSION_TIMEOUT:
        session.state, session.data = MENU, {}
    session.last_inbound_at = now

    home = find_home(wa_id)
    if home is None:
        session.state, session.data = MENU, {}
        session.save()
        client.send_text(
            wa_id,
            "Hello! This number is not registered with Smart Estate. "
            "Please ask your estate office to add this WhatsApp number to your home.",
        )
        return

    kind = message.get("type")
    text, choice = "", None
    if kind == "text":
        text = (message.get("text", {}).get("body") or "").strip()
    elif kind == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        choice = reply.get("id")
    elif kind == "button":  # quick-reply button on a template
        choice = message.get("button", {}).get("payload")
    else:
        client.send_text(wa_id, "Sorry, I can only read text and menu choices for now.")
        session.save()
        show_menu(session, home)
        return

    if text.lower() in RESET_WORDS:
        show_menu(session, home)
        return

    handler = STATE_HANDLERS.get(session.state, handle_menu)
    handler(session, home, text, choice)


# ---------------------------------------------------------------- menu

def show_menu(session, home, intro=None):
    session.state, session.data = MENU, {}
    session.save()
    name = home.resident.name if home.resident else "there"
    body = intro or f"Hi {name}, welcome to Smart Estate ({home.address}). What would you like to do?"
    client.send_list(
        session.wa_id,
        body,
        "Menu",
        [
            ("book", "Book a visitor", "Get a gate code for someone visiting you"),
            ("visitors", "My visitors", "See or cancel upcoming visitors"),
            ("repair", "Report a repair", "Log a fault or complaint with the estate"),
            ("help", "Help", "How this works"),
        ],
        section_title="Smart Estate",
    )


def handle_menu(session, home, text, choice):
    if choice == "book":
        return start_booking(session, home)
    if choice == "visitors":
        return show_visitors(session, home)
    if choice == "repair":
        return start_repair(session, home)
    if choice == "help":
        client.send_text(
            session.wa_id,
            "Smart Estate on WhatsApp:\n"
            "• Book a visitor: you get a code; forward it to your visitor to show at the gate.\n"
            "• My visitors: see who is expected and cancel a booking.\n"
            "• Report a repair: the estate office is notified.\n"
            "Type *menu* at any time to start again.",
        )
        return show_menu(session, home, intro="Anything else?")
    if choice and choice.startswith("cancel_"):
        return cancel_visit(session, home, choice)
    return show_menu(session, home)


# ---------------------------------------------------------------- book a visitor

def start_booking(session, home):
    session.state, session.data = BOOK_NAME, {}
    session.save()
    client.send_text(session.wa_id, "What is your visitor's full name?\n(Type *menu* to cancel.)")


def handle_book_name(session, home, text, choice):
    name = " ".join(text.split())
    if len(name) < 2:
        client.send_text(session.wa_id, "Please type your visitor's full name.")
        return
    session.data["visitor_name"] = name[:MAX_NAME_LENGTH]
    session.state = BOOK_VISITOR_PHONE
    session.save()
    client.send_text(
        session.wa_id,
        f"What is {name}'s mobile number? I'll SMS them the gate code.\n(Type *skip* to forward the code yourself.)",
    )


def handle_book_visitor_phone(session, home, text, choice):
    if text.lower() in SKIP_WORDS:
        session.data["visitor_phone"] = None
    else:
        number = zimbabwe_mobile(text)
        if not number:
            client.send_text(session.wa_id, "That doesn't look like a Zimbabwean mobile number. Try e.g. 0772 123 456, or type *skip*.")
            return
        session.data["visitor_phone"] = number
    ask_transport(session, home)


def ask_transport(session, home):
    name = session.data["visitor_name"]
    session.state = BOOK_TRANSPORT
    session.save()
    transports = list(TransportType.objects.filter(status=True).order_by("id")[:10])
    if not transports:
        session.data["transport_id"] = None
        return ask_confirm(session, home)
    if len(transports) <= 3:
        client.send_buttons(session.wa_id, f"How is {name} coming?", [(f"tr_{t.id}", t.name) for t in transports])
    else:
        client.send_list(session.wa_id, f"How is {name} coming?", "Choose", [(f"tr_{t.id}", t.name, None) for t in transports])


def handle_book_transport(session, home, text, choice):
    transport = None
    if choice and choice.startswith("tr_"):
        transport = TransportType.objects.filter(id=choice[3:], status=True).first()
    elif text:
        transport = TransportType.objects.filter(name__iexact=text, status=True).first()
    if transport is None:
        client.send_text(session.wa_id, "Please choose one of the options above.")
        return
    session.data["transport_id"] = transport.id
    if any(word in transport.name.lower() for word in ("driv", "car", "vehicle")):
        session.state = BOOK_VEHICLE
        session.save()
        client.send_text(session.wa_id, "What is the car's registration number? (Type *skip* if you don't know.)")
        return
    ask_confirm(session, home)


def handle_book_vehicle(session, home, text, choice):
    reg = "".join(text.upper().split())
    session.data["vehicle"] = "" if reg.lower() in SKIP_WORDS else reg[:20]
    ask_confirm(session, home)


def ask_confirm(session, home):
    session.state = BOOK_CONFIRM
    session.save()
    data = session.data
    transport = TransportType.objects.filter(id=data.get("transport_id")).first()
    lines = [f"Visitor: {data['visitor_name']}", f"Home: {home.address} (stand {home.stand.stand_number})"]
    if transport:
        lines.append(f"Coming: {transport.name}")
    if data.get("vehicle"):
        lines.append(f"Car: {data['vehicle']}")
    if data.get("visitor_phone"):
        lines.append(f"Code sent by SMS to: {data['visitor_phone']}")
    client.send_buttons(
        session.wa_id,
        "Please confirm the booking:\n" + "\n".join(lines),
        [("confirm_yes", "Confirm"), ("confirm_no", "Cancel")],
    )


def handle_book_confirm(session, home, text, choice):
    if choice == "confirm_no" or text.lower() in {"no", "n"}:
        return show_menu(session, home, intro="Booking cancelled. What would you like to do?")
    if choice != "confirm_yes" and text.lower() not in {"yes", "y", "confirm"}:
        client.send_text(session.wa_id, "Please tap *Confirm* or *Cancel*.")
        return

    data = session.data
    transport = TransportType.objects.filter(id=data.get("transport_id")).first() or TransportType.objects.order_by("id").first()
    status = initial_status(VisitStatus, ["Coming", "Expected", "Pending"])
    if transport is None or status is None:
        client.send_text(session.wa_id, "Sorry, booking is not set up yet. Please contact the estate office.")
        return show_menu(session, home)

    code = new_visit_code()
    visit = Visit.objects.create(
        stand_number=home.stand.stand_number,
        home=home.address,
        visit_code=code,
        resident_phone_number=local_phone(session.wa_id),
        visitor_name=data["visitor_name"],
        visitor_vehicle_reg_number=data.get("vehicle") or None,
        visitor_phone_number=data.get("visitor_phone"),
        transport_type=transport,
        visit_status=status,
    )
    host = home.resident.name if home.resident else ""
    if send_code_to_visitor(visit, host_name=host):
        delivery = f"I've sent the code to {data['visitor_name']} by SMS. You can also forward this message."
    else:
        delivery = f"Forward this message to {data['visitor_name']}."
    client.send_text(
        session.wa_id,
        f"Booked ✅\nGate code: *{code}*\n\n"
        f"{delivery} They show the code and their ID at the gate. I'll message you when they arrive.",
    )
    show_menu(session, home, intro="Anything else?")


# ---------------------------------------------------------------- my visitors

def upcoming_visits(home):
    return Visit.objects.filter(stand_number=home.stand.stand_number, status=True).order_by("-date_created")[:9]


def show_visitors(session, home):
    visits = list(upcoming_visits(home))
    if not visits:
        return show_menu(session, home, intro="You have no visitors booked. What would you like to do?")
    rows = []
    for visit in visits:
        arrived = visit.date_arrived is not None
        when = timezone.localtime(visit.date_arrived if arrived else visit.date_created).strftime("%d %b %H:%M")
        if arrived:
            rows.append((f"inside_{visit.id}", visit.visitor_name, f"Arrived {when} · code {visit.visit_code}"))
        else:
            rows.append((f"cancel_{visit.id}", visit.visitor_name, f"Booked {when} · code {visit.visit_code} · tap to cancel"))
    rows.append(("back", "Back to menu", None))
    session.state = MENU
    session.save()
    client.send_list(session.wa_id, "Your visitors. Tap one that has not arrived yet to cancel it.", "Visitors", rows, section_title="Visitors")


def cancel_visit(session, home, choice):
    visit = Visit.objects.filter(
        id=choice.removeprefix("cancel_"), stand_number=home.stand.stand_number, status=True, date_arrived__isnull=True
    ).first()
    if visit is None:
        return show_menu(session, home, intro="That booking can no longer be cancelled. What would you like to do?")
    visit.status = False
    visit.save(update_fields=["status"])
    show_menu(session, home, intro=f"Cancelled the booking for {visit.visitor_name} (code {visit.visit_code}). Anything else?")


# ---------------------------------------------------------------- report a repair

def start_repair(session, home):
    categories = list(ComplaintCategory.objects.filter(status=True).order_by("name")[:10])
    if not categories:
        session.state, session.data = REPAIR_DESCRIPTION, {"category_id": None}
        session.save()
        client.send_text(session.wa_id, "Please describe the problem.")
        return
    session.state, session.data = REPAIR_CATEGORY, {}
    session.save()
    client.send_list(session.wa_id, "What kind of problem is it?", "Choose", [(f"cat_{c.id}", c.name, None) for c in categories], section_title="Categories")


def handle_repair_category(session, home, text, choice):
    category = None
    if choice and choice.startswith("cat_"):
        category = ComplaintCategory.objects.filter(id=choice[4:], status=True).first()
    if category is None:
        client.send_text(session.wa_id, "Please choose a category from the list.")
        return
    session.data["category_id"] = category.id
    session.state = REPAIR_DESCRIPTION
    session.save()
    client.send_text(session.wa_id, f"{category.name}: please describe the problem and where it is.")


def handle_repair_description(session, home, text, choice):
    if len(text) < 3:
        client.send_text(session.wa_id, "Please type a short description of the problem.")
        return
    category = ComplaintCategory.objects.filter(id=session.data.get("category_id")).first() or ComplaintCategory.objects.order_by("id").first()
    status = initial_status(ComplaintStatus, ["Pending", "Open", "New"])
    if category is None or status is None:
        client.send_text(session.wa_id, "Sorry, repairs are not set up yet. Please contact the estate office.")
        return show_menu(session, home)
    code = random_numbers()
    Complain.objects.create(
        stand_number=home.stand.stand_number,
        home=home.address,
        complain_code=code,
        resident_phone_number=local_phone(session.wa_id),
        description=text[:MAX_DESCRIPTION_LENGTH],
        complaint_category=category,
        compalint_status=status,
    )
    client.send_text(session.wa_id, f"Thank you. Your report is logged with reference *{code}*. The estate office will follow up.")
    show_menu(session, home, intro="Anything else?")


STATE_HANDLERS = {
    MENU: handle_menu,
    BOOK_NAME: handle_book_name,
    BOOK_VISITOR_PHONE: handle_book_visitor_phone,
    BOOK_TRANSPORT: handle_book_transport,
    BOOK_VEHICLE: handle_book_vehicle,
    BOOK_CONFIRM: handle_book_confirm,
    REPAIR_CATEGORY: handle_repair_category,
    REPAIR_DESCRIPTION: handle_repair_description,
}
