import logging
from urllib.parse import parse_qsl

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record, usd
from estates.context import use_estate
from home.models import Home
from smartEstateBackend.permissions import IsAdminRole

from . import paynow
from .accounts import account, all_accounts, in_zig
from .models import ExchangeRate, Invoice, Payment
from .notifications import send_payment_failed, send_receipt
from .serializers import ExchangeRateSerializer, GenerateSerializer, InvoiceSerializer, PaymentSerializer, VoidSerializer

logger = logging.getLogger(__name__)


class ExchangeRates(generics.ListCreateAPIView):
    """POST for a day that already has a rate replaces it (to correct a typo)."""

    permission_classes = [IsAdminRole]
    serializer_class = ExchangeRateSerializer
    pagination_class = None

    def get_queryset(self):
        return ExchangeRate.objects.all()[:100]

    def create(self, request, *args, **kwargs):
        existing = ExchangeRate.objects.filter(effective_from=request.data.get("effective_from")).first() if request.data.get("effective_from") else None
        serializer = self.get_serializer(existing, data=request.data)
        serializer.is_valid(raise_exception=True)
        rate = serializer.save(created_by=request.user)
        record("rate.set", f"Set the ZiG rate to {rate.zig_per_usd} per USD from {rate.effective_from:%d %b %Y}", rate, area="money",
               replaced=str(existing.zig_per_usd) if existing else None)
        return Response(serializer.data, status=200 if existing else 201)


class Invoices(generics.ListCreateAPIView):
    """GET ?home=<id>&period=YYYY-MM&void=true|false ; POST one invoice."""

    permission_classes = [IsAdminRole]
    serializer_class = InvoiceSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Invoice.objects.order_by("-issued_on", "-id")
        params = self.request.query_params
        if params.get("home"):
            qs = qs.filter(home_id=params["home"])
        if params.get("period"):
            try:
                year, month = map(int, params["period"].split("-"))
                qs = qs.filter(period__year=year, period__month=month)
            except ValueError:
                return qs.none()
        if params.get("void") in {"true", "false"}:
            qs = qs.filter(void=params["void"] == "true")
        return qs[:2000]

    def perform_create(self, serializer):
        invoice = serializer.save(created_by=self.request.user)
        record("invoice.created", f"Billed {usd(invoice.amount_usd)} to {invoice.address}: {invoice.description}", invoice, area="money")


class GenerateLevies(APIView):
    """Bill every active home for one month. `preview: true` only counts."""

    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = GenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        period = data["period"]
        if data["due_date"] < period:
            return Response({"due_date": "The due date must be in or after the month billed."}, status=400)
        billed = set(Invoice.objects.filter(kind=Invoice.LEVY, period=period, void=False).values_list("home_id", flat=True))
        homes = [h for h in Home.objects.filter(status=True).select_related("stand").order_by("stand__stand_number") if h.id not in billed]
        result = {"period": period.strftime("%Y-%m"), "to_create": len(homes), "already_billed": len(billed)}
        if data["preview"]:
            return Response(result)
        description = data.get("description") or f"Levy for {period:%B %Y}"
        with transaction.atomic():
            for home in homes:
                Invoice.objects.create(
                    home=home, stand_number=home.stand.stand_number, address=home.address, kind=Invoice.LEVY,
                    period=period, description=description, amount_usd=data["amount_usd"], due_date=data["due_date"],
                    created_by=request.user,
                )
        result["created"] = len(homes)
        record("levies.generated", f"Billed the levy for {period:%B %Y} to {len(homes)} homes at {usd(data['amount_usd'])} each",
               area="money", period=period, homes=len(homes), amount_usd=data["amount_usd"])
        return Response(result, status=201)


class VoidInvoice(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, id):
        invoice = get_object_or_404(Invoice, pk=id)
        serializer = VoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if invoice.void:
            return Response({"detail": "This invoice is already void."}, status=400)
        invoice.void = True
        invoice.void_reason = serializer.validated_data["reason"]
        invoice.save(update_fields=["void", "void_reason"])
        record("invoice.voided", f"Cancelled invoice {invoice.number} ({usd(invoice.amount_usd)}, {invoice.address}): {invoice.void_reason}",
               invoice, area="money")
        return Response(InvoiceSerializer(invoice).data)


class Accounts(APIView):
    """Every home's balance and arrears."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        rows = all_accounts()
        totals = {
            "invoiced": sum(r["invoiced"] for r in rows),
            "paid": sum(r["paid"] for r in rows),
            "balance": sum(r["balance"] for r in rows),
            "arrears": sum(r["arrears"] for r in rows),
            "homes_in_arrears": sum(1 for r in rows if r["arrears"] > 0),
        }
        zig, rate = in_zig(totals["balance"])
        return Response({"totals": totals, "zig_rate": rate, "accounts": rows})


class AccountStatement(APIView):
    """One home: invoices with what is paid on each, payments, running balance."""

    permission_classes = [IsAdminRole]

    def get(self, request, home_id):
        home = get_object_or_404(Home.objects.select_related("stand", "resident"), pk=home_id)
        acc = account(home)
        payments = Payment.objects.filter(home=home).select_related("recorded_by", "home__stand")
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
            "home": {"id": home.id, "address": home.address, "stand_number": home.stand.stand_number,
                     "resident": f"{home.resident.name} {home.resident.surname}" if home.resident else ""},
            "invoiced": acc["invoiced"], "paid": acc["paid"], "balance": acc["balance"], "arrears": acc["arrears"],
            "balance_zig": zig, "zig_rate": rate,
            "invoices": [
                {**InvoiceSerializer(r["invoice"]).data, "paid": r["paid"], "outstanding": r["outstanding"], "state": r["state"]}
                for r in acc["invoices"]
            ],
            "payments": PaymentSerializer(payments, many=True).data,
            "statement": entries,
        })


class Payments(generics.ListCreateAPIView):
    """GET ?home=<id>&status=paid ; POST records a payment taken at the office."""

    permission_classes = [IsAdminRole]
    serializer_class = PaymentSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Payment.objects.select_related("home__stand", "recorded_by")
        params = self.request.query_params
        if params.get("home"):
            qs = qs.filter(home_id=params["home"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs[:2000]

    def perform_create(self, serializer):
        payment = serializer.save(recorded_by=self.request.user, status=Payment.PENDING, channel=Payment.OFFICE)
        payment.mark_paid()
        record("payment.recorded", f"Recorded {usd(payment.amount_usd)} {payment.get_method_display()} for {payment.home.address} (receipt {payment.receipt_number})",
               payment, area="money", currency=payment.currency, amount=payment.amount, reference=payment.reference)
        if self.request.data.get("send_receipt", True) not in (False, "false", "0"):
            send_receipt(payment)


class ReversePayment(APIView):
    """POST {reason}: a payment recorded by mistake (wrong home or amount) stops counting. Kept in the history."""

    permission_classes = [IsAdminRole]

    def post(self, request, id):
        reason = str(request.data.get("reason") or "").strip()[:200]
        if len(reason) < 3:
            return Response({"reason": "Say why the payment is reversed."}, status=400)
        with transaction.atomic():
            payment = get_object_or_404(Payment.objects.select_for_update().select_related("home"), pk=id)
            if payment.status != Payment.PAID:
                return Response({"detail": "Only a paid payment can be reversed."}, status=400)
            payment.status = Payment.CANCELLED
            payment.failure_reason = f"Reversed by {request.user.get_full_name() or request.user.username}: {reason}"
            payment.save(update_fields=["status", "failure_reason"])
        record("payment.reversed", f"Reversed {usd(payment.amount_usd)} (receipt {payment.receipt_number}) for {payment.home.address}: {reason}",
               payment, area="money")
        return Response(PaymentSerializer(payment).data)


class PaynowResult(APIView):
    """Paynow posts payment results here (form-encoded, signed with the integration key)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request, payment_id):
        payment = Payment.all_estates.filter(pk=payment_id).select_related("estate").first()
        if payment is None:
            return HttpResponse(status=404)
        with use_estate(payment.estate):
            return self.apply(request, payment)

    def apply(self, request, payment):
        pairs = parse_qsl(request.body.decode("utf-8", errors="replace"), keep_blank_values=True)
        before = payment.status
        try:
            with transaction.atomic():
                payment = Payment.objects.select_for_update().select_related("estate").get(pk=payment.pk)
                after = paynow.apply_status(payment, pairs)
        except paynow.PaynowError as exc:
            logger.warning("Rejected Paynow result for payment %s: %s", payment.pk, exc)
            return HttpResponse(status=400)
        if before == Payment.PENDING and after == Payment.PAID:
            send_receipt(payment)
        elif before == Payment.PENDING and after in (Payment.FAILED, Payment.CANCELLED):
            send_payment_failed(payment)
        return HttpResponse("OK")
