"""
Messages the estate sends to residents without them asking first.

WhatsApp only allows free-form messages within 24 hours of the resident's
last message. Outside that window an approved template must be used
(WHATSAPP_TEMPLATE_VISITOR_ARRIVED). With neither available, nothing is sent.
"""

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import client
from .models import WhatsAppSession

logger = logging.getLogger(__name__)

SERVICE_WINDOW = timedelta(hours=24)


def international(phone):
    """0772111111 / +263 772 111 111 -> 263772111111."""
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("263"):
        return digits
    if digits.startswith("0"):
        return "263" + digits[1:]
    return "263" + digits


def _within_window(wa_id):
    session = WhatsAppSession.objects.filter(wa_id=wa_id).first()
    return bool(session and session.last_inbound_at and timezone.now() - session.last_inbound_at < SERVICE_WINDOW)


def notify(phone, text, template="", template_params=(), buttons=None, template_buttons=()):
    """
    Message a resident who may not have written to the bot recently.

    Inside the 24-hour window: `text` (as buttons if given). Outside it: the
    approved `template` with `template_params` (and quick-reply payloads
    `template_buttons`), if one is configured.
    Returns True if WhatsApp accepted a message. Never raises.
    """
    from estates.context import in_sandbox

    if not settings.WHATSAPP_ENABLED and not in_sandbox():
        return False
    try:
        wa_id = international(phone)
        if not wa_id:
            return False
        if _within_window(wa_id):
            if buttons:
                return client.send_buttons(wa_id, text, buttons)
            return client.send_text(wa_id, text)
        if template:
            return client.send_template(wa_id, template, list(template_params), button_payloads=template_buttons)
        logger.info("No open WhatsApp window or template for %s; message not sent", wa_id)
        return False
    except Exception:  # a failed notification must never break the caller
        logger.exception("Could not send WhatsApp notification")
        return False


def notify_visitor_arrived(visit):
    """Tell the resident their visitor is at the gate."""
    when = timezone.localtime(visit.date_arrived or timezone.now()).strftime("%H:%M")
    return notify(
        visit.resident_phone_number,
        f"🚪 {visit.visitor_name} arrived at the gate at {when} (code {visit.visit_code}).",
        settings.WHATSAPP_TEMPLATE_VISITOR_ARRIVED,
        [visit.visitor_name, when, visit.visit_code],
    )
