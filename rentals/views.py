import datetime

from django.db import transaction
from django.db.models import Max
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from complaint.models import Complain
from home.models import Home
from levy.accounts import in_zig
from levy.models import Invoice, Payment
from levy.notifications import send_receipt
from levy.serializers import InvoiceSerializer, PaymentSerializer
from owner.models import Owner
from parameters.models.models_home_status import HomeStatus
from parameters.models.models_stand_status import StandStatus
from resident.models import Resident
from smartEstateBackend.permissions import IsAdminRole
from stand.models import Stand

from . import services
from .models import Expense, Lease
from .serializers import (
    BillSerializer, EndLeaseSerializer, ExpenseSerializer, LeaseSerializer, PropertySerializer, StartLeaseSerializer, local,
)

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
DOCUMENT_SIGNATURES = {b"%PDF": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


def first_status(model, names):
    for name in names:
        found = model.objects.filter(name__iexact=name, status=True).first()
        if found:
            return found
    return model.objects.filter(status=True).order_by("id").first() or model.objects.create(name=names[0])


def owner_from(data, user):
    if data.get("owner"):
        return data["owner"]
    return Owner.objects.create(
        name=data["owner_name"], surname=data["owner_surname"], id_number="", phone_number1=data["owner_phone"],
        authorized_by=user,
    )


class Properties(APIView):
    """GET the rent roll: every property with its tenant, rent and arrears. POST adds a property."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        rows, totals = services.rent_roll()
        return Response({"totals": totals, "properties": rows})

    @transaction.atomic
    def post(self, request):
        serializer = PropertySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        number = data.get("reference") or (Stand.objects.aggregate(top=Max("stand_number"))["top"] or 0) + 1
        if Stand.objects.filter(stand_number=number, status=True).exists():
            return Response({"reference": "Another property already has that number."}, status=400)
        stand = Stand.objects.create(
            stand_number=number, stand_status=first_status(StandStatus, ["Vacant", "Occupied"]), authorized_by=request.user
        )
        home = Home.objects.create(
            owner=owner_from(data, request.user), stand=stand, address=data["address"],
            home_status=first_status(HomeStatus, ["Vacant"]), authorized_by=request.user,
        )
        return Response({"home_id": home.id, "reference": number, "address": home.address}, status=201)


class PropertyDetail(APIView):
    """One property: who rents it now, past tenants, repairs and costs."""

    permission_classes = [IsAdminRole]

    def get(self, request, home_id):
        home = get_object_or_404(Home.objects.select_related("stand", "owner", "resident"), pk=home_id)
        today = timezone.localdate()
        leases = []
        for lease in Lease.objects.filter(home=home).select_related("tenant", "home__stand"):
            acc = services.lease_account(lease, today)
            leases.append({**LeaseSerializer(lease).data, "balance": acc["balance"], "arrears": acc["arrears"], "paid": acc["paid"]})
        repairs = Complain.objects.filter(stand_number=home.stand.stand_number, status=True).select_related(
            "complaint_category", "compalint_status"
        ).order_by("-date_created")[:20]
        year = services.statement(today.replace(month=1, day=1), today)
        mine = next((r for r in year["properties"] if r["home_id"] == home.id), None)
        return Response({
            "home_id": home.id, "reference": home.stand.stand_number, "address": home.address, "active": home.status,
            "owner": {"id": home.owner_id, "name": services.full_name(home.owner), "phone": home.owner.phone_number1},
            "leases": leases,
            "expenses": ExpenseSerializer(Expense.objects.filter(home=home)[:50], many=True).data,
            "repairs": [
                {"id": c.id, "code": c.complain_code, "category": c.complaint_category.name, "description": c.description,
                 "status": c.compalint_status.name, "date": c.date_created}
                for c in repairs
            ],
            "this_year": {k: mine[k] for k in ("income", "expenses", "fee", "net")} if mine else None,
        })

    @transaction.atomic
    def put(self, request, home_id):
        home = get_object_or_404(Home, pk=home_id)
        serializer = PropertySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "address" in data:
            home.address = data["address"]
        if data.get("owner") or data.get("owner_name"):
            if not data.get("owner") and not (data.get("owner_surname") and data.get("owner_phone")):
                return Response({"owner": "Give the new owner's name, surname and mobile number."}, status=400)
            home.owner = owner_from(data, request.user)
        if "active" in request.data:
            active = request.data["active"] in (True, "true", "1", 1)
            if not active and Lease.objects.filter(home=home, status=Lease.ACTIVE).exists():
                return Response({"active": "End the lease before removing this property."}, status=400)
            home.status = active
        home.save()
        return Response({"home_id": home.id, "address": home.address, "active": home.status})


class Leases(APIView):
    """GET ?status=active|ended&home=<id> ; POST starts a lease."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = Lease.objects.select_related("tenant", "home__stand")
        if request.query_params.get("status") in (Lease.ACTIVE, Lease.ENDED):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("home"):
            qs = qs.filter(home_id=request.query_params["home"])
        return Response(LeaseSerializer(qs[:1000], many=True).data)

    @transaction.atomic
    def post(self, request):
        serializer = StartLeaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        home = data.pop("home")
        tenant = data.pop("tenant", None)
        new = {key: data.pop(key, "") for key in ("tenant_name", "tenant_surname", "tenant_phone", "tenant_id_number")}
        if tenant is None:
            tenant = Resident.objects.create(
                name=new["tenant_name"], surname=new["tenant_surname"], id_number=new["tenant_id_number"] or "",
                phone_number1=new["tenant_phone"], authorized_by=request.user,
            )
        try:
            lease = services.start_lease(home, tenant, user=request.user, first_rent_usd=data.pop("first_rent_usd", None), **data)
        except services.LeaseError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(LeaseSerializer(lease).data, status=201)


class LeaseDetail(APIView):
    """GET the lease with its statement; PUT changes the rent, dates, deposit received or notes."""

    permission_classes = [IsAdminRole]

    def lease(self, id):
        return get_object_or_404(Lease.objects.select_related("tenant", "home__stand"), pk=id)

    def get(self, request, id):
        lease = self.lease(id)
        acc = services.lease_account(lease)
        payments = Payment.objects.filter(lease=lease).select_related("recorded_by", "home__stand")
        entries = [
            {"date": r["invoice"].issued_on, "kind": "invoice", "id": r["invoice"].id, "number": r["invoice"].number,
             "description": r["invoice"].description, "debit": r["invoice"].amount_usd, "credit": None}
            for r in acc["invoices"]
        ] + [
            {"date": timezone.localtime(p.paid_at).date(), "kind": "payment", "id": p.id, "number": p.receipt_number,
             "description": f"Payment, {p.get_method_display()}", "debit": None, "credit": p.amount_usd}
            for p in payments if p.status == Payment.PAID
        ]
        entries.sort(key=lambda e: (e["date"], 0 if e["kind"] == "invoice" else 1, e["id"]))
        running = 0
        for entry in entries:
            running += (entry["debit"] or 0) - (entry["credit"] or 0)
            entry["balance"] = running
        zig, rate = in_zig(acc["balance"]) if acc["balance"] > 0 else (None, None)
        return Response({
            "lease": LeaseSerializer(lease).data,
            "invoiced": acc["invoiced"], "paid": acc["paid"], "balance": acc["balance"], "arrears": acc["arrears"],
            "balance_zig": zig, "zig_rate": rate,
            "invoices": [
                {**InvoiceSerializer(r["invoice"]).data, "paid": r["paid"], "outstanding": r["outstanding"], "state": r["state"]}
                for r in acc["invoices"]
            ],
            "payments": PaymentSerializer(payments, many=True).data,
            "statement": entries,
        })

    def put(self, request, id):
        lease = self.lease(id)
        if lease.status != Lease.ACTIVE:
            return Response({"detail": "This lease has ended and can no longer be changed."}, status=400)
        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EndLease(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, id):
        lease = get_object_or_404(Lease, pk=id)
        serializer = EndLeaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            lease = services.end_lease(
                lease, data["ended_on"], user=request.user, deposit_returned_usd=data["deposit_returned_usd"],
                deposit_deducted_usd=data["deposit_deducted_usd"], reason=data.get("reason", ""),
            )
        except services.LeaseError as exc:
            return Response({"detail": str(exc)}, status=400)
        acc = services.lease_account(lease)
        return Response({**LeaseSerializer(lease).data, "balance": acc["balance"]})


class LeasePayments(APIView):
    """Record money received for one lease (also a past tenant settling up)."""

    permission_classes = [IsAdminRole]

    def post(self, request, id):
        lease = get_object_or_404(Lease.objects.select_related("home"), pk=id)
        serializer = PaymentSerializer(data={**request.data, "home": lease.home_id})
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["method"] == Payment.DEPOSIT:
            return Response({"method": "Money kept from a deposit is recorded when the lease ends."}, status=400)
        payment = serializer.save(lease=lease, recorded_by=request.user, status=Payment.PENDING, channel=Payment.OFFICE)
        payment.mark_paid()
        if request.data.get("send_receipt", True) not in (False, "false", "0"):
            send_receipt(payment)
        return Response(PaymentSerializer(payment).data, status=201)


class LeaseDocument(APIView):
    """The signed agreement: PDF or a photo, up to 5 MB. Staff only."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, id):
        lease = get_object_or_404(Lease, pk=id)
        if not lease.document:
            return Response({"detail": "No agreement has been uploaded."}, status=404)
        response = FileResponse(lease.document.open("rb"), content_type=lease.document_type or "application/octet-stream")
        response["Content-Disposition"] = f'inline; filename="lease-{lease.pk}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request, id):
        lease = get_object_or_404(Lease, pk=id)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"file": "Choose a file."}, status=400)
        if upload.size > MAX_DOCUMENT_BYTES:
            return Response({"file": "The file is larger than 5 MB."}, status=400)
        head = upload.read(8)
        upload.seek(0)
        kind = next((mime for signature, mime in DOCUMENT_SIGNATURES.items() if head.startswith(signature)), None)
        if kind is None:
            return Response({"file": "Upload a PDF, or a JPEG or PNG photo."}, status=400)
        if lease.document:
            lease.document.delete(save=False)
        extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[kind]
        lease.document.save(f"agreement.{extension}", upload, save=False)
        lease.document_name = (upload.name or "agreement")[:120]
        lease.document_type = kind
        lease.save(update_fields=["document", "document_name", "document_type"])
        return Response(LeaseSerializer(lease).data)

    def delete(self, request, id):
        lease = get_object_or_404(Lease, pk=id)
        if lease.document:
            lease.document.delete(save=False)
        lease.document_name = lease.document_type = ""
        lease.save(update_fields=["document", "document_name", "document_type"])
        return Response(status=204)


class BillRent(APIView):
    """Bill every tenant for one month. `preview: true` only counts."""

    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = BillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year, month = map(int, serializer.validated_data["period"].split("-"))
        preview = serializer.validated_data["preview"]
        count, already = services.bill_rent(datetime.date(year, month, 1), user=request.user, preview=preview)
        body = {"period": serializer.validated_data["period"], "to_create": count, "already_billed": already}
        if not preview:
            body["created"] = count
        return Response(body, status=200 if preview else 201)


class Expenses(generics.ListCreateAPIView):
    """GET ?home=<id>&from=YYYY-MM-DD&to=YYYY-MM-DD"""

    permission_classes = [IsAdminRole]
    serializer_class = ExpenseSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Expense.objects.select_related("home")
        params = self.request.query_params
        if params.get("home"):
            qs = qs.filter(home_id=params["home"])
        try:
            if params.get("from"):
                qs = qs.filter(date__gte=datetime.date.fromisoformat(params["from"]))
            if params.get("to"):
                qs = qs.filter(date__lte=datetime.date.fromisoformat(params["to"]))
        except ValueError:
            return qs.none()
        return qs[:2000]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ExpenseDetail(generics.DestroyAPIView):
    permission_classes = [IsAdminRole]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return Expense.objects.all()


class Statement(APIView):
    """GET ?from=YYYY-MM-DD&to=YYYY-MM-DD&owner=<id>: money in and out per property."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        today = timezone.localdate()
        try:
            start = datetime.date.fromisoformat(request.query_params.get("from") or services.month_start(today).isoformat())
            end = datetime.date.fromisoformat(request.query_params.get("to") or today.isoformat())
        except ValueError:
            return Response({"detail": "Dates look like 2026-01-31."}, status=400)
        if end < start:
            return Response({"detail": "The end date is before the start date."}, status=400)
        owner = None
        if request.query_params.get("owner"):
            owner = get_object_or_404(Owner, pk=request.query_params["owner"])
        body = services.statement(start, end, owner=owner)
        body["owner"] = {"id": owner.id, "name": services.full_name(owner), "phone": owner.phone_number1} if owner else None
        return Response(body)


class People(APIView):
    """Owners and tenants on file, for the pick-lists."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response({
            "owners": [
                {"id": o.id, "name": services.full_name(o), "phone": local(o.phone_number1)}
                for o in Owner.objects.filter(status=True).order_by("name", "surname")[:2000]
            ],
            "tenants": [
                {"id": r.id, "name": services.full_name(r), "phone": local(r.phone_number1)}
                for r in Resident.objects.filter(status=True).order_by("name", "surname")[:2000]
            ],
        })
