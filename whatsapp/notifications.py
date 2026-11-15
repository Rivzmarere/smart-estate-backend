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


def notify_visitor_arrived(visit):
    """Tell the resident their visitor is at the gate. Never raises."""
    if not settings.WHATSAPP_ENABLED:
        return False
    try:
        wa_id = international(visit.resident_phone_number)
        if not wa_id:
            return False
        when = timezone.localtime(visit.date_arrived or timezone.now()).strftime("%H:%M")
        if _within_window(wa_id):
            return client.send_text(wa_id, f"🚪 {visit.visitor_name} arrived at the gate at {when} (code {visit.visit_code}).")
        template = settings.WHATSAPP_TEMPLATE_VISITOR_ARRIVED
        if template:
            return client.send_template(wa_id, template, [visit.visitor_name, when, visit.visit_code])
        logger.info("No open WhatsApp window or template; arrival of visit %s not sent", visit.pk)
        return False
    except Exception:  # a failed notification must never block the gate
        logger.exception("Could not send arrival notification for visit %s", getattr(visit, "pk", None))
        return False
