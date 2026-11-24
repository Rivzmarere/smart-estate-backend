"""Asking residents to approve walk-in visitors, and recording their answer."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from visit.models import Visit
from visit.utilities import random_numbers
from whatsapp.notifications import notify

from .models import WalkInRequest

APPROVE_PREFIX = "walkin_yes_"
DECLINE_PREFIX = "walkin_no_"


def ask_resident(walk_in):
    """Send the Approve / Decline question. Returns True if WhatsApp accepted it."""
    who = walk_in.visitor_name + (f" ({walk_in.vehicle})" if walk_in.vehicle else "")
    sent = notify(
        walk_in.resident_phone,
        f"🚪 {who} is at the gate asking to visit you at {walk_in.address}. Let them in?",
        settings.WHATSAPP_TEMPLATE_WALK_IN,
        [who],
        buttons=[(f"{APPROVE_PREFIX}{walk_in.pk}", "Approve"), (f"{DECLINE_PREFIX}{walk_in.pk}", "Decline")],
        template_buttons=[f"{APPROVE_PREFIX}{walk_in.pk}", f"{DECLINE_PREFIX}{walk_in.pk}"],
    )
    if sent:
        walk_in.whatsapp_sent = True
        walk_in.save(update_fields=["whatsapp_sent"])
    return sent


def _expected_status():
    for name in ("Coming", "Expected", "Pending"):
        found = VisitStatus.objects.filter(name__iexact=name, status=True).first()
        if found:
            return found
    return VisitStatus.objects.filter(status=True).order_by("id").first()


def _new_code():
    for _ in range(10):
        code = random_numbers()
        if not Visit.objects.filter(visit_code=code, status=True).exists():
            return code
    return random_numbers()


def answer(walk_in_id, approve, via):
    """
    Record the resident's answer. On approval a visit is created (expected at
    the gate), which the guard books in as usual.
    Returns (walk_in, changed). Only a pending, unexpired request can change.
    """
    with transaction.atomic():
        walk_in = WalkInRequest.objects.select_for_update().select_related("home__stand").filter(pk=walk_in_id).first()
        if walk_in is None:
            return None, False
        if walk_in.expire_if_stale() != WalkInRequest.PENDING:
            return walk_in, False
        walk_in.answered_via = via
        walk_in.answered_at = timezone.now()
        if not approve:
            walk_in.status = WalkInRequest.DECLINED
            walk_in.save(update_fields=["status", "answered_via", "answered_at"])
            return walk_in, True
        transport = walk_in.transport_type or TransportType.objects.filter(status=True).order_by("id").first()
        status = _expected_status()
        if transport is None or status is None:
            raise ValueError("Visit statuses and transport types must be set up first.")
        walk_in.visit = Visit.objects.create(
            stand_number=walk_in.stand_number,
            home=walk_in.address,
            visit_code=_new_code(),
            resident_phone_number=walk_in.resident_phone,
            visitor_name=walk_in.visitor_name,
            visitor_national_id=walk_in.visitor_national_id,
            visitor_vehicle_reg_number=walk_in.vehicle or None,
            transport_type=transport,
            visit_status=status,
        )
        walk_in.status = WalkInRequest.APPROVED
        walk_in.save(update_fields=["status", "answered_via", "answered_at", "visit"])
        return walk_in, True
