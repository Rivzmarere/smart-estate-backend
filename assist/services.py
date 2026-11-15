"""Raising emergencies and running office conversations."""

from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from sms.sender import send_sms
from whatsapp.models import WhatsAppSession
from whatsapp.notifications import notify

from .models import Conversation, ConversationMessage, EmergencyAlert

# Zimbabwe's national emergency numbers.
NATIONAL_NUMBERS = "Police 995 · Ambulance 994 · Fire 993 · Emergency 999 (112 from a mobile)"

# A second alert from the same home within this time adds to the first one.
REPEAT_WINDOW = timedelta(minutes=10)

HANDOFF_STATE = "handoff"


def resident_name(home):
    return f"{home.resident.name} {home.resident.surname}" if home.resident else ""


def raise_emergency(home, wa_id, kind):
    """Returns (alert, created). Never raises because a notification failed."""
    recent = EmergencyAlert.objects.filter(
        home=home, status__in=[EmergencyAlert.OPEN, EmergencyAlert.ACKNOWLEDGED], created_at__gte=timezone.now() - REPEAT_WINDOW
    ).first()
    if recent:
        return recent, False
    alert = EmergencyAlert.objects.create(
        home=home, stand_number=home.stand.stand_number, address=home.address, resident_name=resident_name(home),
        wa_id=wa_id, kind=kind,
    )
    estate = home.estate
    text = (
        f"EMERGENCY ({alert.get_kind_display()}) at {home.address}, stand {home.stand.stand_number}. "
        f"Resident {alert.resident_name or ''} {local(wa_id)}. Raised {timezone.localtime(alert.created_at):%H:%M} via WhatsApp."
    )
    sent = [number for number in estate.emergency_numbers if send_sms(number, text)]
    alert.sms_sent_to = ", ".join(sent)[:200]
    alert.save(update_fields=["sms_sent_to"])
    return alert, True


def add_emergency_details(alert, text):
    alert.details = (alert.details + "\n" if alert.details else "") + text[:500]
    alert.save(update_fields=["details"])
    for number in alert.home.estate.emergency_numbers:
        send_sms(number, f"EMERGENCY update, {alert.address}: {text[:300]}")


def tell_resident_about_alert(alert):
    if alert.status == EmergencyAlert.ACKNOWLEDGED:
        who = alert.acknowledged_by.get_full_name() or alert.acknowledged_by.username if alert.acknowledged_by else "Security"
        text = f"🚨 {who} has seen your emergency alert and is responding."
    else:
        text = "✅ Your emergency alert has been marked as resolved. Type *menu* if you need anything else."
    return notify(alert.wa_id, text) or send_sms(alert.wa_id, f"Smart Estate: {text}")


def local(wa_id):
    digits = "".join(ch for ch in str(wa_id) if ch.isdigit())
    return "0" + digits[3:] if digits.startswith("263") else digits


# ---------------------------------------------------------------- office chat

def open_conversation(home, wa_id):
    """The resident's open conversation, or a new one. Returns (conversation, created)."""
    conversation = Conversation.objects.filter(home=home, wa_id=wa_id, status=Conversation.OPEN).first()
    if conversation:
        return conversation, False
    conversation = Conversation.objects.create(
        home=home, stand_number=home.stand.stand_number, address=home.address, resident_name=resident_name(home),
        wa_id=wa_id, last_message_at=timezone.now(),
    )
    office = home.estate.office_phone
    if office:
        send_sms(office, f"Smart Estate: {conversation.resident_name or 'A resident'} ({home.address}) wants to chat with the office. Open the Inbox.")
    return conversation, True


def record_resident_message(conversation, text):
    ConversationMessage.objects.create(conversation=conversation, direction=ConversationMessage.FROM_RESIDENT, text=text[:4000])
    Conversation.objects.filter(pk=conversation.pk).update(unread=F("unread") + 1, last_message_at=timezone.now())


def office_reply(conversation, text, user):
    """Send the office's reply on WhatsApp. Returns the message (delivered tells whether WhatsApp took it)."""
    template = getattr(settings, "WHATSAPP_TEMPLATE_OFFICE_MESSAGE", "")
    delivered = notify(conversation.wa_id, f"🏢 *{conversation.home.estate.name} office:* {text}", template, [text[:1000]])
    message = ConversationMessage.objects.create(
        conversation=conversation, direction=ConversationMessage.FROM_OFFICE, text=text[:4000], sent_by=user, delivered=delivered,
    )
    conversation.last_message_at = timezone.now()
    if conversation.status == Conversation.CLOSED:
        conversation.status, conversation.closed_at, conversation.closed_by = Conversation.OPEN, None, None
    conversation.save(update_fields=["last_message_at", "status", "closed_at", "closed_by"])
    # The resident's next message should reach the office, not the menu.
    WhatsAppSession.objects.filter(wa_id=conversation.wa_id).update(state=HANDOFF_STATE, data={"conversation_id": conversation.pk})
    return message


def close_conversation(conversation, user):
    conversation.status = Conversation.CLOSED
    conversation.closed_at = timezone.now()
    conversation.closed_by = user
    conversation.save(update_fields=["status", "closed_at", "closed_by"])
    session = WhatsAppSession.objects.filter(wa_id=conversation.wa_id).first()
    if session and session.state == HANDOFF_STATE and session.data.get("conversation_id") == conversation.pk:
        session.state, session.data = "menu", {}
        session.save(update_fields=["state", "data"])
        notify(conversation.wa_id, "The estate office has closed this chat. Type *menu* for options, or *office* to write to them again.")
