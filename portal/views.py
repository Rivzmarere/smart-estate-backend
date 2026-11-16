"""
The residents' portal API: everything the WhatsApp bot does, plus the household.
Every endpoint below /resident/ (except signing in) needs a resident token,
and every home is checked against the signed-in phone number on each request.
"""

from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from assist import services as assist
from assist.models import Conversation, EmergencyAlert
from complaint.models import Complain, ComplaintPhoto
from estates.context import ALL, current_estate
from gatepass import services as walk_ins
from gatepass.models import WalkInRequest
from levy import paynow
from levy.accounts import account, in_zig
from levy.models import Payment
from levy.services import pending_payment, start_payment
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from sms.sender import zimbabwe_mobile
from visit.messaging import send_code_to_visitor
from visit.models import Visit
from whatsapp.bot import PHOTO_TYPES, initial_status, new_visit_code
from whatsapp.notifications import international

from . import auth, household
from .access import homes_for_phone
from .models import HouseholdMember, HouseholdRequest

MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png", b"RIFF": "image/webp"}


def local(phone):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return "0" + digits[3:] if digits.startswith("263") else digits


def person(user):
    return (user.get_full_name() or user.username) if user else ""


# ---------------------------------------------------------------- signing in

class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        phone = zimbabwe_mobile(value)
        if not phone:
            raise serializers.ValidationError("Enter a Zimbabwean mobile number, e.g. 0772 123 456.")
        return phone


class VerifySerializer(PhoneSerializer):
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "The code has 6 digits."})


def portal_estate():
    estate = current_estate()
    return None if estate is None or estate is ALL else estate


class RequestCode(APIView):
    """POST {phone}: text a sign-in code to a number registered with this estate."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        estate = portal_estate()
        if estate is None:
            return Response({"detail": "Open the portal from your estate's link."}, status=400)
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        # Same answer whether or not the number is registered, so the form cannot be used to look people up.
        if homes_for_phone(phone) and not auth.issue_code(estate, phone):
            return Response({"detail": "Too many codes asked for. Please wait 15 minutes."}, status=429)
        return Response({"sent": True, "message": f"If {local(phone)} is registered with {estate.name}, a code is on its way."})


class VerifyCode(APIView):
    """POST {phone, code}: a resident token."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        estate = portal_estate()
        if estate is None:
            return Response({"detail": "Open the portal from your estate's link."}, status=400)
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        if not auth.check_code(estate, phone, serializer.validated_data["code"]):
            return Response({"code": ["That code is wrong or has expired. Ask for a new one."]}, status=400)
        if not homes_for_phone(phone):
            return Response({"detail": "This number is not linked to a home any more."}, status=403)
        return Response({"token": auth.make_token(estate, phone), "phone": local(phone)})


# ---------------------------------------------------------------- base view

class ResidentView(APIView):
    authentication_classes = [auth.ResidentAuthentication]
    permission_classes = [auth.IsResident]
    action = None  # permission needed on the home (see access.PERMISSIONS)

    @property
    def phone(self):
        return self.request.user.phone

    def access(self, home_id, action=None):
        """The signed-in resident's access to this home, or 404 (never reveals other homes)."""
        action = action or self.action
        for item in homes_for_phone(self.phone):
            if item.home.pk == int(home_id) and (action is None or item.can(action)):
                return item
        from django.http import Http404

        raise Http404


def home_card(item):
    home = item.home
    return {
        "id": home.pk,
        "address": home.address,
        "stand_number": home.stand.stand_number,
        "role": item.label,
        "can": {action: item.can(action) for action in ("visitors", "repairs", "levy", "household", "tenancy", "chat", "emergency")},
    }


class Me(ResidentView):
    def get(self, request):
        estate = request.user.estate
        return Response({
            "phone": local(self.phone),
            "estate": {"name": estate.name, "slug": estate.slug, "office_phone": estate.office_phone},
            "homes": [home_card(item) for item in homes_for_phone(self.phone)],
        })


class HomeOverview(ResidentView):
    def get(self, request, home_id):
        item = self.access(home_id)
        home = item.home
        today = timezone.localdate()
        data = {
            **home_card(item),
            "resident": f"{home.resident.name} {home.resident.surname}" if home.resident else "",
            "visitors_today": Visit.objects.filter(stand_number=home.stand.stand_number, status=True, date_created__date=today).count(),
            "inside_now": Visit.objects.filter(stand_number=home.stand.stand_number, date_arrived__isnull=False, date_depature__isnull=True, status=True).count(),
            "open_repairs": Complain.objects.filter(stand_number=home.stand.stand_number, status=True).exclude(
                compalint_status__name__iregex=r"^(resolved|closed|done|completed)$"
            ).count(),
            "walk_ins_waiting": sum(1 for w in WalkInRequest.objects.filter(home=home, status=WalkInRequest.PENDING) if w.expire_if_stale() == WalkInRequest.PENDING),
            "pending_requests": HouseholdRequest.objects.filter(home=home, status=HouseholdRequest.PENDING).count(),
        }
        if item.can("levy"):
            acc = account(home)
            data["levy"] = {"balance": acc["balance"], "arrears": acc["arrears"]}
        return Response(data)


# ---------------------------------------------------------------- visitors

class BookSerializer(serializers.Serializer):
    visitor_name = serializers.CharField(max_length=60, min_length=2)
    visitor_phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    transport_type = serializers.PrimaryKeyRelatedField(queryset=TransportType.objects.filter(status=True))
    vehicle = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_visitor_phone_number(self, value):
        if not value:
            return None
        phone = zimbabwe_mobile(value)
        if not phone:
            raise serializers.ValidationError("That isn't a Zimbabwean mobile number.")
        return phone


def visit_row(v):
    if not v.status:
        state = "cancelled"
    elif v.date_depature:
        state = "left"
    elif v.date_arrived:
        state = "inside"
    else:
        state = "expected"
    return {
        "id": v.id, "visitor_name": v.visitor_name, "visit_code": v.visit_code, "state": state,
        "vehicle": v.visitor_vehicle_reg_number or "", "transport": v.transport_type.name if v.transport_type_id else "",
        "booked_at": v.date_created, "arrived_at": v.date_arrived, "left_at": v.date_depature,
    }


class Visitors(ResidentView):
    action = "visitors"

    def get(self, request, home_id):
        home = self.access(home_id).home
        visits = Visit.objects.filter(stand_number=home.stand.stand_number).select_related("transport_type").order_by("-date_created")[:30]
        return Response([visit_row(v) for v in visits])

    def post(self, request, home_id):
        home = self.access(home_id).home
        serializer = BookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        status = initial_status(VisitStatus, ["Coming", "Expected", "Pending"])
        if status is None:
            return Response({"detail": "Bookings are not set up yet. Please contact the estate office."}, status=400)
        visit = Visit.objects.create(
            stand_number=home.stand.stand_number, home=home.address, visit_code=new_visit_code(),
            resident_phone_number=local(self.phone), visitor_name=" ".join(data["visitor_name"].split()),
            visitor_phone_number=data.get("visitor_phone_number"), visitor_vehicle_reg_number="".join((data.get("vehicle") or "").upper().split()) or None,
            transport_type=data["transport_type"], visit_status=status,
        )
        host = f"{home.resident.name}" if home.resident else ""
        sms_sent = send_code_to_visitor(visit, host_name=host)
        return Response({**visit_row(visit), "sms_sent": sms_sent}, status=201)


class CancelVisit(ResidentView):
    action = "visitors"

    def post(self, request, home_id, visit_id):
        home = self.access(home_id).home
        visit = get_object_or_404(Visit, pk=visit_id, stand_number=home.stand.stand_number)
        if visit.date_arrived or not visit.status:
            return Response({"detail": "This booking can no longer be cancelled."}, status=409)
        visit.status = False
        visit.save(update_fields=["status"])
        return Response(visit_row(visit))


class WalkIns(ResidentView):
    action = "visitors"

    def get(self, request, home_id):
        home = self.access(home_id).home
        rows = []
        for w in WalkInRequest.objects.filter(home=home).order_by("-created_at")[:10]:
            w.expire_if_stale()
            rows.append({"id": w.id, "visitor_name": w.visitor_name, "vehicle": w.vehicle, "status": w.status,
                         "status_label": w.get_status_display(), "created_at": w.created_at, "expires_at": w.expires_at})
        return Response(rows)


class AnswerWalkIn(ResidentView):
    action = "visitors"

    def post(self, request, home_id, walk_in_id):
        home = self.access(home_id).home
        approve = request.data.get("approve")
        if not isinstance(approve, bool):
            return Response({"approve": "Send true or false."}, status=400)
        get_object_or_404(WalkInRequest, pk=walk_in_id, home=home)
        walk_in, changed = walk_ins.answer(walk_in_id, approve, WalkInRequest.WHATSAPP)
        if not changed:
            return Response({"detail": f"This request is already {walk_in.get_status_display().lower()}."}, status=409)
        return Response({"id": walk_in.id, "status": walk_in.status, "visit_code": walk_in.visit.visit_code if walk_in.visit else None})


# ---------------------------------------------------------------- levy

class Levy(ResidentView):
    action = "levy"

    def get(self, request, home_id):
        home = self.access(home_id).home
        acc = account(home)
        currencies = paynow.available_currencies(home.estate)
        zig, rate = in_zig(acc["balance"]) if acc["balance"] > 0 else (None, None)
        waiting = pending_payment(home)
        return Response({
            "balance": acc["balance"], "arrears": acc["arrears"], "invoiced": acc["invoiced"], "paid": acc["paid"],
            "balance_zig": zig, "zig_rate": rate, "can_pay": bool(currencies), "currencies": currencies,
            "pending_payment": {"id": waiting.id, "amount_usd": waiting.amount_usd, "phone": waiting.phone} if waiting else None,
            "invoices": [
                {"id": r["invoice"].id, "number": r["invoice"].number, "description": r["invoice"].description,
                 "amount_usd": r["invoice"].amount_usd, "due_date": r["invoice"].due_date, "outstanding": r["outstanding"], "state": r["state"]}
                for r in reversed(acc["invoices"])
            ][:24],
            "payments": [
                {"id": p.id, "receipt_number": p.receipt_number, "amount": p.amount, "currency": p.currency, "amount_usd": p.amount_usd,
                 "method": p.get_method_display(), "status": p.status, "paid_at": p.paid_at, "created_at": p.created_at}
                for p in Payment.objects.filter(home=home).order_by("-created_at")[:24]
            ],
        })


class PaySerializer(serializers.Serializer):
    amount_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1.00"), max_value=Decimal("10000.00"))
    currency = serializers.ChoiceField(choices=[Payment.USD, Payment.ZWG], default=Payment.USD)
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        if not paynow.method_for_phone(value):
            raise serializers.ValidationError("Use an EcoCash (077/078) or OneMoney (071) number.")
        return local(zimbabwe_mobile(value))


class Pay(ResidentView):
    action = "levy"

    def post(self, request, home_id):
        home = self.access(home_id).home
        serializer = PaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["currency"] not in paynow.available_currencies(home.estate):
            return Response({"currency": ["Payments in that currency are not available."]}, status=400)
        if pending_payment(home):
            return Response({"detail": "A payment request is already waiting. Approve it on your phone, or try again in a few minutes."}, status=409)
        try:
            payment, instructions = start_payment(home, data["amount_usd"], data["currency"], data["phone"], wa_id=international(self.phone))
        except paynow.PaynowError as exc:
            return Response({"detail": f"The payment could not be started: {exc}"}, status=400)
        return Response({"id": payment.id, "status": payment.status, "amount": payment.amount, "currency": payment.currency,
                         "phone": payment.phone, "method": payment.get_method_display(), "instructions": instructions}, status=201)


class PaymentStatus(ResidentView):
    action = "levy"

    def get(self, request, home_id, payment_id):
        home = self.access(home_id).home
        p = get_object_or_404(Payment, pk=payment_id, home=home)
        return Response({"id": p.id, "status": p.status, "receipt_number": p.receipt_number, "failure_reason": p.failure_reason})


# ---------------------------------------------------------------- repairs

def sniff_image(data):
    for signature, mime in IMAGE_SIGNATURES.items():
        if data.startswith(signature) and (mime != "image/webp" or data[8:12] == b"WEBP"):
            return mime
    return None


class Repairs(ResidentView):
    action = "repairs"

    def get(self, request, home_id):
        home = self.access(home_id).home
        complaints = Complain.objects.filter(stand_number=home.stand.stand_number, status=True).select_related(
            "compalint_status", "complaint_category"
        ).prefetch_related("photos").order_by("-date_created")[:20]
        return Response([
            {"id": c.id, "reference": c.complain_code, "category": c.complaint_category.name, "status": c.compalint_status.name,
             "description": c.description, "photos": c.photos.count(), "created_at": c.date_created, "updated_at": c.date_updated}
            for c in complaints
        ])

    def post(self, request, home_id):
        home = self.access(home_id).home
        category = ComplaintCategory.objects.filter(pk=request.data.get("category"), status=True).first()
        description = (request.data.get("description") or "").strip()
        errors = {}
        if category is None:
            errors["category"] = ["Choose a category."]
        if len(description) < 5:
            errors["description"] = ["Please describe the problem."]
        photos = request.FILES.getlist("photos")[:MAX_PHOTOS + 1]
        if len(photos) > MAX_PHOTOS:
            errors["photos"] = [f"Send at most {MAX_PHOTOS} photos."]
        checked = []
        for upload in photos:
            if upload.size > MAX_PHOTO_BYTES:
                errors["photos"] = ["Each photo must be under 5 MB."]
                break
            data = upload.read()
            mime = sniff_image(data)
            if mime not in PHOTO_TYPES:
                errors["photos"] = ["Photos must be JPEG, PNG or WebP."]
                break
            checked.append((data, mime))
        if errors:
            return Response(errors, status=400)
        status = initial_status(ComplaintStatus, ["Pending", "Open", "New"])
        from visit.utilities import random_numbers

        with transaction.atomic():
            complaint = Complain.objects.create(
                stand_number=home.stand.stand_number, home=home.address, complain_code=random_numbers(),
                resident_phone_number=local(self.phone), description=description[:1000], complaint_category=category,
                compalint_status=status,
            )
            for n, (data, mime) in enumerate(checked, start=1):
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]
                photo = ComplaintPhoto(complaint=complaint, content_type=mime)
                photo.image.save(f"{complaint.complain_code}-{n}{ext}", ContentFile(data), save=True)
        return Response({"id": complaint.id, "reference": complaint.complain_code, "photos": len(checked)}, status=201)


# ---------------------------------------------------------------- household

def request_row(r):
    return {"id": r.id, "kind": r.kind, "summary": household.describe(r), "status": r.status, "status_label": r.get_status_display(),
            "office_note": r.office_note, "created_at": r.created_at, "decided_at": r.decided_at}


class Household(ResidentView):
    def get(self, request, home_id):
        item = self.access(home_id)
        home = item.home
        members = HouseholdMember.objects.filter(home=home, active=True)
        return Response({
            "can_manage": item.can("household"),
            "can_change_tenancy": item.can("tenancy"),
            "needs_approval": home.estate.household_approval,
            "owner": f"{home.owner.name} {home.owner.surname}" if item.can("tenancy") or item.can("household") else None,
            "resident": {"name": f"{home.resident.name} {home.resident.surname}", "phone": home.resident.phone_number1 or ""} if home.resident else None,
            "members": [
                {"id": m.id, "name": m.full_name, "phone": local(m.phone), "relationship": m.relationship,
                 "relationship_label": m.get_relationship_display(), "can_book_visitors": m.can_book_visitors}
                for m in members
            ],
            "requests": [request_row(r) for r in HouseholdRequest.objects.filter(home=home)[:20]],
        })


class HouseholdRequests(ResidentView):
    def post(self, request, home_id):
        item = self.access(home_id)
        data = dict(request.data)
        kind = data.pop("kind", None)
        req = household.submit(item, kind, data, self.phone)
        return Response(request_row(req), status=201)


class CancelHouseholdRequest(ResidentView):
    def post(self, request, home_id, request_id):
        home = self.access(home_id).home
        req = get_object_or_404(HouseholdRequest, pk=request_id, home=home, status=HouseholdRequest.PENDING)
        req.status = HouseholdRequest.CANCELLED
        req.save(update_fields=["status"])
        return Response(request_row(req))


# ---------------------------------------------------------------- office chat and emergencies

def message_row(m):
    return {"id": m.id, "from": "me" if m.direction == "in" else "office", "text": m.text,
            "sent_by": person(m.sent_by) if m.direction == "out" else "", "created_at": m.created_at}


class Chat(ResidentView):
    action = "chat"

    def conversation(self, home, create=False):
        wa_id = international(self.phone)
        convo = Conversation.objects.filter(home=home, wa_id=wa_id, channel=Conversation.PORTAL).order_by("-created_at").first()
        if (convo is None or convo.status == Conversation.CLOSED) and create:
            convo, _ = assist.open_conversation(home, wa_id, channel=Conversation.PORTAL)
        return convo

    def get(self, request, home_id):
        home = self.access(home_id).home
        convo = self.conversation(home)
        return Response({"open": bool(convo and convo.status == Conversation.OPEN),
                         "messages": [message_row(m) for m in convo.messages.select_related("sent_by")] if convo else []})

    def post(self, request, home_id):
        home = self.access(home_id).home
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"text": ["Write a message."]}, status=400)
        convo = self.conversation(home, create=True)
        assist.record_resident_message(convo, text[:4000])
        return Response({"messages": [message_row(m) for m in convo.messages.select_related("sent_by")]}, status=201)


class Emergency(ResidentView):
    action = "emergency"

    def post(self, request, home_id):
        home = self.access(home_id).home
        kind = request.data.get("kind")
        if kind not in dict(EmergencyAlert.KINDS):
            return Response({"kind": ["Choose the type of emergency."]}, status=400)
        alert, created = assist.raise_emergency(home, international(self.phone), kind)
        details = (request.data.get("details") or "").strip()
        if details:
            assist.add_emergency_details(alert, details)
        return Response({"id": alert.id, "created": created, "status": alert.status, "created_at": alert.created_at}, status=201 if created else 200)
