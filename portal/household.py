"""
Household changes from the portal.

Taking access away (removing a member) happens at once. Giving access
(a new member, a new main resident) and a resident moving out wait for the
estate office when the estate has household_approval switched on.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from resident.models import Resident
from sms.sender import send_sms, zimbabwe_mobile
from whatsapp.notifications import notify

from .models import HouseholdMember, HouseholdRequest

MAX_MEMBERS = 12
IMMEDIATE = {HouseholdRequest.REMOVE_MEMBER}


def local(phone):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return "0" + digits[3:] if digits.startswith("263") else digits


class AddMemberSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=60, min_length=2)
    surname = serializers.CharField(max_length=60, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20)
    relationship = serializers.ChoiceField(choices=HouseholdMember.RELATIONSHIPS, default=HouseholdMember.FAMILY)
    can_book_visitors = serializers.BooleanField(default=True)

    def validate_phone(self, value):
        phone = zimbabwe_mobile(value)
        if not phone:
            raise serializers.ValidationError("Enter a Zimbabwean mobile number, e.g. 0772 123 456.")
        return phone


class RemoveMemberSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()


class NewResidentSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=60, min_length=2)
    surname = serializers.CharField(max_length=60, min_length=2)
    phone = serializers.CharField(max_length=20)
    id_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    move_in = serializers.DateField(required=False, allow_null=True)

    def validate_phone(self, value):
        phone = zimbabwe_mobile(value)
        if not phone:
            raise serializers.ValidationError("Enter a Zimbabwean mobile number, e.g. 0772 123 456.")
        return phone


class NoDetails(serializers.Serializer):
    move_out = serializers.DateField(required=False, allow_null=True)


DETAIL_SERIALIZERS = {
    HouseholdRequest.ADD_MEMBER: AddMemberSerializer,
    HouseholdRequest.REMOVE_MEMBER: RemoveMemberSerializer,
    HouseholdRequest.NEW_RESIDENT: NewResidentSerializer,
    HouseholdRequest.RESIDENT_LEAVES: NoDetails,
}

WHO_MAY_ASK = {
    HouseholdRequest.ADD_MEMBER: "household",
    HouseholdRequest.REMOVE_MEMBER: "household",
    HouseholdRequest.NEW_RESIDENT: "tenancy",
    HouseholdRequest.RESIDENT_LEAVES: "tenancy",
}


def describe(req):
    d = req.details
    if req.kind == HouseholdRequest.ADD_MEMBER:
        return f"Add {d.get('name', '')} {d.get('surname', '')} ({local(d.get('phone', ''))}) as {dict(HouseholdMember.RELATIONSHIPS).get(d.get('relationship'), 'member').lower()}".replace("  ", " ")
    if req.kind == HouseholdRequest.REMOVE_MEMBER:
        member = HouseholdMember.objects.filter(pk=d.get("member_id")).first()
        return f"Remove {member.full_name if member else 'a member'}"
    if req.kind == HouseholdRequest.NEW_RESIDENT:
        when = f" from {d['move_in']}" if d.get("move_in") else ""
        return f"New main resident: {d.get('name')} {d.get('surname')} ({local(d.get('phone', ''))}){when}"
    return "Main resident moving out" + (f" on {d['move_out']}" if d.get("move_out") else "")


def submit(access, kind, data, phone):
    """Validate and record a request; apply it now if no approval is needed. Returns the request."""
    if kind not in DETAIL_SERIALIZERS:
        raise serializers.ValidationError({"kind": "Unknown change."})
    if not access.can(WHO_MAY_ASK[kind]):
        raise serializers.ValidationError({"kind": "Only the home's owner can change who lives there." if WHO_MAY_ASK[kind] == "tenancy" else "You can't change this household."})
    detail = DETAIL_SERIALIZERS[kind](data=data)
    detail.is_valid(raise_exception=True)
    details = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in detail.validated_data.items()}
    home = access.home

    if kind == HouseholdRequest.ADD_MEMBER:
        if HouseholdMember.objects.filter(home=home, active=True).count() >= MAX_MEMBERS:
            raise serializers.ValidationError({"kind": f"A home can have at most {MAX_MEMBERS} household members."})
        if HouseholdMember.objects.filter(home=home, active=True, phone=details["phone"]).exists():
            raise serializers.ValidationError({"phone": "That number is already in this household."})
    if kind == HouseholdRequest.REMOVE_MEMBER and not HouseholdMember.objects.filter(home=home, pk=details["member_id"], active=True).exists():
        raise serializers.ValidationError({"member_id": "That person is not in this household."})
    if kind == HouseholdRequest.RESIDENT_LEAVES and home.resident_id is None:
        raise serializers.ValidationError({"kind": "Nobody is recorded as living there."})
    if HouseholdRequest.objects.filter(home=home, kind=kind, status=HouseholdRequest.PENDING, details=details).exists():
        raise serializers.ValidationError({"kind": "You already asked for this; the office will reply."})

    req = HouseholdRequest.objects.create(
        home=home, kind=kind, details=details, requested_by_phone=phone, requested_by_role=access.label,
    )
    if kind in IMMEDIATE or not home.estate.household_approval:
        apply(req)
    return req


@transaction.atomic
def apply(req, user=None):
    """Carry out a request. Raises ValidationError if it no longer makes sense."""
    home = req.home
    d = req.details
    if req.kind == HouseholdRequest.ADD_MEMBER:
        HouseholdMember.objects.create(
            home=home, name=d["name"], surname=d.get("surname", ""), phone=d["phone"],
            relationship=d.get("relationship", HouseholdMember.FAMILY), can_book_visitors=d.get("can_book_visitors", True),
        )
    elif req.kind == HouseholdRequest.REMOVE_MEMBER:
        HouseholdMember.objects.filter(home=home, pk=d["member_id"]).update(active=False)
    elif req.kind == HouseholdRequest.NEW_RESIDENT:
        resident = Resident.objects.create(
            name=d["name"], surname=d["surname"], id_number=d.get("id_number", ""), phone_number1=local(d["phone"]),
            authorized_by=user,
        )
        home.resident = resident
        home.save(update_fields=["resident"])
    elif req.kind == HouseholdRequest.RESIDENT_LEAVES:
        home.resident = None
        home.save(update_fields=["resident"])
    req.status = HouseholdRequest.APPROVED
    req.decided_by = user
    req.decided_at = timezone.now()
    req.save(update_fields=["status", "decided_by", "decided_at"])
    return req


def decide(req, approve, user, note=""):
    if req.status != HouseholdRequest.PENDING:
        raise serializers.ValidationError({"status": "This request has already been dealt with."})
    if approve:
        apply(req, user)
    else:
        req.status = HouseholdRequest.REJECTED
        req.decided_by = user
        req.decided_at = timezone.now()
    req.office_note = note[:300]
    req.save(update_fields=["status", "decided_by", "decided_at", "office_note"])
    outcome = "approved" if approve else "not approved"
    text = f"{req.home.estate.name}: your request \"{describe(req)}\" was {outcome}." + (f" Note: {note}" if note else "")
    if not notify(req.requested_by_phone, text):
        send_sms(req.requested_by_phone, text)
    return req

