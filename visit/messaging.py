"""
Messages about visits, sent by WhatsApp where possible and SMS otherwise.
"""

from django.utils import timezone

from sms.sender import send_sms
from whatsapp.notifications import notify_visitor_arrived as whatsapp_visitor_arrived


def send_code_to_visitor(visit, host_name=""):
    """Text the gate code to the visitor's phone, if one was given."""
    if not visit.visitor_phone_number:
        return False
    host = f"{host_name} has" if host_name else "You have been"
    verb = "booked your visit to" if host_name else "booked to visit"
    message = (
        f"Smart Estate: {host} {verb} {visit.home}. "
        f"Gate code: {visit.visit_code}. Show this code and your ID at the gate."
    )
    return send_sms(visit.visitor_phone_number, message)


def notify_visitor_arrived(visit):
    """Tell the resident their visitor is at the gate: WhatsApp first, SMS if that is not possible."""
    if whatsapp_visitor_arrived(visit):
        return True
    when = timezone.localtime(visit.date_arrived or timezone.now()).strftime("%H:%M")
    return send_sms(
        visit.resident_phone_number,
        f"Smart Estate: {visit.visitor_name} arrived at the gate at {when} (code {visit.visit_code}).",
    )
