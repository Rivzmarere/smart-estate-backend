"""
Smart Estate WhatsApp bot: menu-driven conversations for residents.

Book a visitor, see / cancel my visitors, report a repair (with photos),
see my repairs, pay the levy by EcoCash / OneMoney, read notices, and answer
walk-in requests from the gate.
The bot identifies the resident by their WhatsApp number, which Meta has
already verified, and only serves numbers registered on a home.
"""

import mimetypes
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.utils import timezone

from assist import services as assist
from assist.models import EmergencyAlert
from complaint.models import Complain, ComplaintPhoto
from estates.context import use_estate
from gatepass import services as walk_ins
from gatepass.models import WalkInRequest
from levy import paynow
from levy.accounts import account, fmt_usd, fmt_zig, in_zig
from levy.models import Payment
from levy.services import pending_payment, start_payment
from notice.models import Notice
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.models.models_provider_category import ProviderCategory
from provider.models import Provider
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from visit.models import Visit
from sms.sender import zimbabwe_mobile
from visit.messaging import send_code_to_visitor
from visit.utilities import random_numbers

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
REPAIR_PHOTO = "repair_photo"
LEVY_CHOICE = "levy_choice"
LEVY_AMOUNT = "levy_amount"
LEVY_CURRENCY = "levy_currency"
LEVY_PHONE = "levy_phone"
EMERGENCY_KIND = "emergency_kind"
EMERGENCY_DETAILS = "emergency_details"
PROVIDER_CATEGORY = "provider_category"
HANDOFF = assist.HANDOFF_STATE

# A half-finished conversation older than this starts again from the menu.
SESSION_TIMEOUT = timedelta(minutes=30)
# A chat with the office stays with the office for a day.
HANDOFF_TIMEOUT = timedelta(hours=24)

RESET_WORDS = {"hi", "hello", "menu", "start", "0", "home", "cancel", "stop", "mhoro", "sawubona"}
SKIP_WORDS = {"skip", "no", "none", "-"}
EMERGENCY_WORDS = {"sos", "emergency", "help me"}
HANDOFF_EXIT_WORDS = {"menu", "cancel", "stop", "bot"}

MAX_NAME_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 1000
MAX_PHOTOS = 3
PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIN_PAYMENT = Decimal("1.00")
MAX_PAYMENT = Decimal("10000.00")


# ---------------------------------------------------------------- lookups

def find_homes(wa_id):
    """Active homes this number belongs to (as resident, household member or owner), in any estate."""
    from portal.access import homes_for_phone

    return [access.home for access in homes_for_phone(wa_id, across_estates=True)]


def find_home(wa_id):
    """The home the bot works with for this number (the first, if there are several), or None."""
    homes = find_homes(wa_id)
    return homes[0] if homes else None


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
    """Process one inbound WhatsApp message object from the webhook, inside the resident's estate."""
    home = find_home(wa_id)
    if home is None:
        return _handle_message(wa_id, message, None)
    with use_estate(home.estate):
        return _handle_message(wa_id, message, home)


def _handle_message(wa_id, message, home):
    session, _ = WhatsAppSession.objects.get_or_create(wa_id=wa_id)
    now = timezone.now()
    timeout = HANDOFF_TIMEOUT if session.state == HANDOFF else SESSION_TIMEOUT
    if session.state != MENU and session.updated_at and now - session.updated_at > timeout:
        session.state, session.data = MENU, {}
    session.last_inbound_at = now

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
    elif kind == "image":
        session.save()
        if session.state == HANDOFF:
            client.send_text(session.wa_id, "I can only pass written messages to the office for now. Please describe it in words.")
            return
        return handle_image(session, home, message.get("image", {}))
    else:
        client.send_text(wa_id, "Sorry, I can only read text and menu choices for now.")
        session.save()
        show_menu(session, home)
        return

    # Walk-in answers can arrive at any point in a conversation.
    if choice and choice.startswith((walk_ins.APPROVE_PREFIX, walk_ins.DECLINE_PREFIX)):
        session.save()
        return answer_walk_in(session, home, choice)

    lowered = text.lower()
    if lowered in EMERGENCY_WORDS:
        return start_emergency(session, home)

    # Talking to the office: everything goes to the office until they say "menu".
    if session.state == HANDOFF and not choice:
        if lowered in HANDOFF_EXIT_WORDS:
            return show_menu(session, home, intro="You're back with the Smart Estate assistant. The office can still reply to you here.")
        return handle_handoff(session, home, text)

    if lowered in RESET_WORDS:
        show_menu(session, home)
        return
    if lowered == "office":
        return start_handoff(session, home)

    handler = STATE_HANDLERS.get(session.state, handle_menu)
    handler(session, home, text, choice)


# ---------------------------------------------------------------- menu

def show_menu(session, home, intro=None):
    session.state, session.data = MENU, {}
    session.save()
    name = home.resident.name if home.resident else "there"
    body = intro or f"Hi {name}, welcome to {home.estate.name} ({home.address}). What would you like to do?"
    client.send_list(
        session.wa_id,
        body,
        "Menu",
        [
            ("book", "Book a visitor", "Get a gate code for someone visiting you"),
            ("visitors", "My visitors", "See or cancel upcoming visitors"),
            ("levy", "Pay levy", "See your balance and pay with EcoCash or OneMoney"),
            ("repair", "Report a repair", "Log a fault or complaint with the estate"),
            ("repairs", "My repairs", "Progress on repairs you reported"),
            ("providers", "Service providers", "Plumbers, electricians and others the estate uses"),
            ("notices", "Estate notices", "Latest news from the estate office"),
            ("office", "Talk to the office", "Chat with a person at the estate office"),
            ("emergency", "🚨 Emergency", "Alert estate security now"),
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
    if choice == "repairs":
        return show_repairs(session, home)
    if choice == "levy":
        return show_levy(session, home)
    if choice == "providers":
        return show_provider_categories(session, home)
    if choice == "office":
        return start_handoff(session, home)
    if choice == "emergency":
        return start_emergency(session, home)
    if choice == "notices":
        return show_notices(session, home)
    if choice == "help":
        client.send_text(
            session.wa_id,
            "Smart Estate on WhatsApp:\n"
            "• Book a visitor: you get a code; forward it to your visitor to show at the gate.\n"
            "• My visitors: see who is expected and cancel a booking.\n"
            "• Pay levy: see what you owe and pay from your EcoCash or OneMoney wallet; the receipt comes here.\n"
            "• Report a repair: the estate office is notified, and you can send photos. I'll tell you when the status changes.\n"
            "• Talk to the office: chat with a person at the estate office.\n"
            "• Emergency: type *SOS* at any time to alert estate security.\n"
            "Type *menu* at any time to start again.",
        )
        return show_menu(session, home, intro="Anything else?")
    if choice and choice.startswith("cancel_"):
        return cancel_visit(session, home, choice)
    return show_menu(session, home)


def show_notices(session, home):
    notices = list(Notice.objects.current()[:3])
    if not notices:
        return show_menu(session, home, intro="There are no estate notices right now. What would you like to do?")
    parts = []
    for notice in notices:
        when = timezone.localtime(notice.publish_at).strftime("%d %b")
        pin = "📌 " if notice.pinned else ""
        body = notice.body if len(notice.body) <= 600 else notice.body[:597] + "…"
        parts.append(f"{pin}*{notice.title}* ({notice.get_category_display()}, {when})\n{body}")
    client.send_text(session.wa_id, "\n\n".join(parts))
    show_menu(session, home, intro="Anything else?")


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
    complaint = Complain.objects.create(
        stand_number=home.stand.stand_number,
        home=home.address,
        complain_code=code,
        resident_phone_number=local_phone(session.wa_id),
        description=text[:MAX_DESCRIPTION_LENGTH],
        complaint_category=category,
        compalint_status=status,
    )
    session.state, session.data = REPAIR_PHOTO, {"complaint_id": complaint.id}
    session.save()
    client.send_buttons(
        session.wa_id,
        f"Thank you. Your report is logged with reference *{code}*. The estate office will follow up, "
        "and I'll message you when its status changes.\n\nIf you can, send a photo of the problem now. It helps the team.",
        [("repair_done", "Done")],
    )


def handle_repair_photo(session, home, text, choice):
    """Waiting for photos; anything other than an image finishes the report."""
    show_menu(session, home, intro="Thanks. Anything else?")


def handle_image(session, home, image):
    if session.state != REPAIR_PHOTO:
        client.send_text(session.wa_id, "Thanks, but I can only take photos as part of a repair report. Tap *Report a repair* first.")
        return show_menu(session, home)
    complaint = Complain.objects.filter(id=session.data.get("complaint_id"), stand_number=home.stand.stand_number).first()
    if complaint is None:
        return show_menu(session, home)
    if complaint.photos.count() >= MAX_PHOTOS:
        client.send_buttons(session.wa_id, f"I already have {MAX_PHOTOS} photos for this report, which is enough. Thank you!", [("repair_done", "Done")])
        return
    data, mime = client.download_media(image.get("id", ""))
    mime = (mime or image.get("mime_type") or "").split(";")[0].strip().lower()
    if not data or mime not in PHOTO_TYPES:
        client.send_buttons(session.wa_id, "Sorry, I couldn't save that photo. Please send it as a normal photo (JPEG or PNG, under 5 MB).", [("repair_done", "Done")])
        return
    extension = mimetypes.guess_extension(mime) or ".jpg"
    photo = ComplaintPhoto(complaint=complaint, content_type=mime, source_media_id=image.get("id", "")[:128])
    photo.image.save(f"{complaint.complain_code}-{complaint.photos.count() + 1}{extension}", ContentFile(data), save=True)
    count = complaint.photos.count()
    more = " Send another, or tap Done." if count < MAX_PHOTOS else ""
    client.send_buttons(session.wa_id, f"Photo added to report {complaint.complain_code} ({count} of {MAX_PHOTOS}).{more}", [("repair_done", "Done")])


def show_repairs(session, home):
    complaints = list(
        Complain.objects.filter(stand_number=home.stand.stand_number, status=True)
        .select_related("compalint_status", "complaint_category").order_by("-date_created")[:5]
    )
    if not complaints:
        return show_menu(session, home, intro="You have no repair reports. What would you like to do?")
    lines = ["Your latest repair reports:"]
    for c in complaints:
        when = timezone.localtime(c.date_created).strftime("%d %b")
        lines.append(f"• *{c.complain_code}* {c.complaint_category.name}: {c.compalint_status.name} (logged {when})")
    client.send_text(session.wa_id, "\n".join(lines))
    show_menu(session, home, intro="Anything else?")


# ---------------------------------------------------------------- walk-in approval

def answer_walk_in(session, home, choice):
    approve = choice.startswith(walk_ins.APPROVE_PREFIX)
    raw_id = choice.removeprefix(walk_ins.APPROVE_PREFIX if approve else walk_ins.DECLINE_PREFIX)
    request = WalkInRequest.all_estates.filter(id=raw_id if raw_id.isdigit() else 0, home__in=find_homes(session.wa_id)).first()
    if request is None:
        client.send_text(session.wa_id, "I couldn't find that gate request.")
        return
    with use_estate(request.estate):
        request, changed = walk_ins.answer(request.id, approve, WalkInRequest.WHATSAPP)
    if not changed:
        already = {
            WalkInRequest.APPROVED: "was already approved",
            WalkInRequest.DECLINED: "was already declined",
            WalkInRequest.EXPIRED: "has expired. If they are still at the gate, the guard can ask again",
        }.get(request.status, "can no longer be changed")
        client.send_text(session.wa_id, f"The request for {request.visitor_name} {already}.")
        return
    if approve:
        client.send_text(session.wa_id, f"✅ Approved. The guard will let {request.visitor_name} in (code {request.visit.visit_code}). I'll tell you when they are inside.")
    else:
        client.send_text(session.wa_id, f"❌ Declined. The guard will not let {request.visitor_name} in.")


# ---------------------------------------------------------------- levy

def show_levy(session, home):
    from portal.access import access_to

    access = access_to(home, session.wa_id)
    if access is None or not access.can("levy"):
        return show_menu(session, home, intro="Only the home's owner and main resident can see the levy account. What would you like to do?")
    acc = account(home)
    balance = acc["balance"]
    if balance <= 0:
        extra = f" You have {fmt_usd(-balance)} credit." if balance < 0 else ""
        return show_menu(session, home, intro=f"Your levy account for {home.address} is up to date ✅.{extra} What would you like to do?")
    lines = [f"Levy account for {home.address}", f"Balance: *{fmt_usd(balance)}*"]
    if acc["arrears"] > 0:
        lines.append(f"Overdue: {fmt_usd(acc['arrears'])}")
    currencies = paynow.available_currencies(home.estate)
    if Payment.ZWG in currencies:
        zig, rate = in_zig(balance)
        if zig is not None:
            lines.append(f"In ZiG: {fmt_zig(zig)} at {rate:,.2f} per USD")
    waiting = pending_payment(home)
    if waiting:
        lines.append(f"\nA payment request for {fmt_usd(waiting.amount_usd)} is waiting on {waiting.phone}. Approve it on that phone, or try again in a few minutes.")
        client.send_text(session.wa_id, "\n".join(lines))
        return show_menu(session, home, intro="Anything else?")
    if not currencies:
        lines.append("\nTo pay, please contact the estate office.")
        client.send_text(session.wa_id, "\n".join(lines))
        return show_menu(session, home, intro="Anything else?")
    session.state, session.data = LEVY_CHOICE, {}
    session.save()
    client.send_buttons(
        session.wa_id,
        "\n".join(lines) + "\n\nHow much would you like to pay?",
        [("levy_all", f"Pay {fmt_usd(balance)}"), ("levy_other", "Another amount"), ("levy_back", "Not now")],
    )


def handle_levy_choice(session, home, text, choice):
    if choice == "levy_all":
        return levy_amount_chosen(session, home, account(home)["balance"])
    if choice == "levy_other":
        session.state = LEVY_AMOUNT
        session.save()
        client.send_text(session.wa_id, "How much would you like to pay, in US dollars? (e.g. 50)")
        return
    if choice == "levy_back":
        return show_menu(session, home)
    if text:
        return handle_levy_amount(session, home, text, choice)
    client.send_text(session.wa_id, "Please tap one of the buttons above.")


def parse_amount(text):
    cleaned = re.sub(r"(?i)usd|us\$|\$|dollars?", "", text).replace(",", "").strip()
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def handle_levy_amount(session, home, text, choice):
    amount = parse_amount(text)
    if amount is None or not (MIN_PAYMENT <= amount <= MAX_PAYMENT):
        client.send_text(session.wa_id, f"Please type an amount in US dollars between {MIN_PAYMENT:.0f} and {MAX_PAYMENT:,.0f}, e.g. 50.")
        return
    levy_amount_chosen(session, home, amount)


def levy_amount_chosen(session, home, amount):
    session.data["amount_usd"] = str(amount)
    currencies = paynow.available_currencies(home.estate)
    zig, _ = in_zig(amount) if Payment.ZWG in currencies else (None, None)
    if Payment.USD in currencies and zig is not None:
        session.state = LEVY_CURRENCY
        session.save()
        client.send_buttons(
            session.wa_id,
            "Which wallet are you paying from?",
            [("cur_USD", fmt_usd(amount)), ("cur_ZWG", fmt_zig(zig))],
        )
        return
    session.data["currency"] = Payment.USD if Payment.USD in currencies else Payment.ZWG
    ask_payer_phone(session, home)


def handle_levy_currency(session, home, text, choice):
    if choice not in ("cur_USD", "cur_ZWG"):
        client.send_text(session.wa_id, "Please tap USD or ZiG.")
        return
    session.data["currency"] = choice[4:]
    ask_payer_phone(session, home)


def ask_payer_phone(session, home):
    session.state = LEVY_PHONE
    session.save()
    own = local_phone(session.wa_id)
    if paynow.method_for_phone(own):
        client.send_buttons(
            session.wa_id,
            "Which number should get the payment prompt?",
            [("payphone_self", f"Use {own}"), ("payphone_other", "Another number")],
        )
    else:
        client.send_text(session.wa_id, "Type the EcoCash or OneMoney number to send the payment prompt to.")


def handle_levy_phone(session, home, text, choice):
    if choice == "payphone_other":
        client.send_text(session.wa_id, "Type the EcoCash or OneMoney number, e.g. 0772 123 456.")
        return
    if choice == "payphone_self":
        phone = local_phone(session.wa_id)
    else:
        number = zimbabwe_mobile(text)
        phone = local_phone(number) if number else None
        if not phone or not paynow.method_for_phone(phone):
            client.send_text(session.wa_id, "That isn't an EcoCash (077/078) or OneMoney (071) number. Please try again, or type *menu*.")
            return
    if not paynow.method_for_phone(phone):
        client.send_text(session.wa_id, "That number can't pay through EcoCash or OneMoney. Type another number.")
        return

    amount = Decimal(session.data["amount_usd"])
    currency = session.data.get("currency", Payment.USD)
    try:
        payment, instructions = start_payment(home, amount, currency, phone, wa_id=session.wa_id)
    except paynow.PaynowError as exc:
        client.send_text(session.wa_id, f"Sorry, I couldn't start the payment: {exc} Please try again later.")
        return show_menu(session, home, intro="Anything else?")
    wallet = payment.get_method_display()
    shown = fmt_zig(payment.amount) if currency == Payment.ZWG else fmt_usd(payment.amount)
    message = (
        f"📲 I've sent a payment request for *{shown}* to {phone}.\n"
        f"Enter your {wallet} PIN on that phone to approve it. Your receipt will come here."
    )
    if instructions:
        message += f"\n\nNo prompt? {instructions}"
    session.state, session.data = MENU, {}
    session.save()
    client.send_text(session.wa_id, message)


# ---------------------------------------------------------------- emergencies

def start_emergency(session, home):
    session.state, session.data = EMERGENCY_KIND, {}
    session.save()
    client.send_list(
        session.wa_id,
        "🚨 What is the emergency? Estate security will be alerted straight away with your address.",
        "Choose",
        [
            ("em_security", "Security / intruder", None),
            ("em_medical", "Medical", None),
            ("em_fire", "Fire", None),
            ("em_other", "Other emergency", None),
            ("em_cancel", "Cancel, no emergency", None),
        ],
        section_title="Emergency",
    )


def handle_emergency_kind(session, home, text, choice):
    kinds = {f"em_{k}": k for k, _ in EmergencyAlert.KINDS}
    if choice == "em_cancel":
        return show_menu(session, home, intro="No alert was sent. What would you like to do?")
    kind = kinds.get(choice)
    if kind is None:
        if text:  # typed instead of tapping: treat as "other" so help is never delayed
            kind = EmergencyAlert.OTHER
        else:
            client.send_text(session.wa_id, "Please choose the type of emergency from the list.")
            return
    alert, created = assist.raise_emergency(home, session.wa_id, kind)
    if text:
        assist.add_emergency_details(alert, text)
    session.state, session.data = EMERGENCY_DETAILS, {"alert_id": alert.id}
    session.save()
    when = timezone.localtime(alert.created_at).strftime("%H:%M")
    first = f"🚨 Alert sent to estate security at {when}. They have your address: {home.address}." if created else (
        f"🚨 Security already has your alert from {when}. I've added this to it."
    )
    office = f"\nEstate office: {home.estate.office_phone}" if home.estate.office_phone else ""
    client.send_text(
        session.wa_id,
        f"{first}\n\nIf a life is in danger, also call: {assist.NATIONAL_NUMBERS}.{office}\n\n"
        "Reply with any details (what is happening, where exactly) and I'll pass them on.",
    )


def handle_emergency_details(session, home, text, choice):
    if choice:
        return handle_menu(session, home, text, choice)
    alert = EmergencyAlert.objects.filter(id=session.data.get("alert_id"), home=home).first()
    if alert is None or not text:
        return show_menu(session, home)
    assist.add_emergency_details(alert, text)
    client.send_text(session.wa_id, "Passed on to security. Send more details any time, or type *menu* when you're done.")


# ---------------------------------------------------------------- service providers

def show_provider_categories(session, home):
    used = Provider.objects.filter(status=True).values_list("provider_category_id", flat=True)
    categories = list(ProviderCategory.objects.filter(id__in=used, status=True).order_by("name")[:9])
    if not categories:
        return show_menu(session, home, intro="The estate has not listed any service providers yet. What would you like to do?")
    session.state, session.data = PROVIDER_CATEGORY, {}
    session.save()
    rows = [(f"pc_{c.id}", c.name, None) for c in categories] + [("back", "Back to menu", None)]
    client.send_list(session.wa_id, "Service providers the estate uses. Which do you need?", "Choose", rows, section_title="Categories")


def handle_provider_category(session, home, text, choice):
    if choice == "back" or not (choice or "").startswith("pc_"):
        return show_menu(session, home)
    category = ProviderCategory.objects.filter(id=choice[3:]).first()
    providers = list(Provider.objects.filter(provider_category=category, status=True).order_by("name")[:10]) if category else []
    if not providers:
        return show_menu(session, home, intro="No one is listed in that category. What would you like to do?")
    lines = [f"*{category.name}*"]
    for p in providers:
        phones = " / ".join(n for n in (p.phone_number1, p.phone_number2) if n)
        lines.append(f"• {p.name} {p.surname}: {phones}")
    lines.append("\nThese are independent businesses; agree the price before work starts.")
    client.send_text(session.wa_id, "\n".join(lines))
    show_menu(session, home, intro="Anything else?")


# ---------------------------------------------------------------- office hand-off

def start_handoff(session, home):
    conversation, created = assist.open_conversation(home, session.wa_id)
    session.state, session.data = HANDOFF, {"conversation_id": conversation.id}
    session.save()
    hours = f" Office hours: {home.estate.office_hours}." if home.estate.office_hours else ""
    client.send_text(
        session.wa_id,
        f"You're now writing to the {home.estate.name} office.{hours} Type your message and a person will reply here.\n"
        "Type *menu* to go back to the assistant.",
    )


def handle_handoff(session, home, text):
    if not text:
        return
    from assist.models import Conversation

    conversation = Conversation.objects.filter(id=session.data.get("conversation_id"), home=home, status=Conversation.OPEN).first()
    if conversation is None:
        conversation, _ = assist.open_conversation(home, session.wa_id)
        session.data = {"conversation_id": conversation.id}
    first_message = not conversation.messages.exists()
    assist.record_resident_message(conversation, text)
    session.save()
    if first_message:
        client.send_text(session.wa_id, "Thanks, the office has your message and will reply here.")


STATE_HANDLERS = {
    MENU: handle_menu,
    BOOK_NAME: handle_book_name,
    BOOK_VISITOR_PHONE: handle_book_visitor_phone,
    BOOK_TRANSPORT: handle_book_transport,
    BOOK_VEHICLE: handle_book_vehicle,
    BOOK_CONFIRM: handle_book_confirm,
    REPAIR_CATEGORY: handle_repair_category,
    REPAIR_DESCRIPTION: handle_repair_description,
    REPAIR_PHOTO: handle_repair_photo,
    LEVY_CHOICE: handle_levy_choice,
    LEVY_AMOUNT: handle_levy_amount,
    LEVY_CURRENCY: handle_levy_currency,
    LEVY_PHONE: handle_levy_phone,
    EMERGENCY_KIND: handle_emergency_kind,
    EMERGENCY_DETAILS: handle_emergency_details,
    PROVIDER_CATEGORY: handle_provider_category,
}
