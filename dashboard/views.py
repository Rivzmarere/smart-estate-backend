"""
The estate dashboard: one call with the numbers the back office home page shows.

Guards get only today's gate; administrators also get money, repairs and
the people and places of the estate. Works for gated estates and rental
portfolios (rentals have no gate, so that part is left out).
"""

import datetime

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from complaint.models import Complain
from estates.context import ALL, current_estate
from estates.org_views import CLOSED_REPAIR, estate_row, summarise
from home.models import Home
from levy.accounts import ZERO
from levy.models import Payment
from provider.models import Provider
from rentals.services import _period_bounds, month_start, next_month
from reports.views import day_bounds
from resident.models import Resident
from smartEstateBackend.permissions import IsAdminOrGuard, is_admin
from stand.models import Stand
from visit.models import Visit
from whitelist.models import WhiteList

MONTHS = 6


def gate_today(today):
    """Visitors booked, arrived, inside and gone today, plus regulars (white list) inside."""
    start, end = day_bounds(today)
    visits = Visit.objects.filter(status=True)
    regulars = WhiteList.objects.filter(status=True)
    return {
        "booked": visits.filter(date_created__gte=start, date_created__lt=end).count(),
        "expected": visits.filter(date_created__gte=start, date_created__lt=end, date_arrived__isnull=True).count(),
        "arrived": visits.filter(date_arrived__gte=start, date_arrived__lt=end).count(),
        "departed": visits.filter(date_depature__gte=start, date_depature__lt=end).count(),
        "inside": visits.filter(date_arrived__isnull=False, date_depature__isnull=True).count(),
        "regulars_inside": regulars.filter(date_depature__isnull=True).count(),
        "regulars_today": regulars.filter(date_arrived__gte=start, date_arrived__lt=end).count(),
    }


def collected_by_month(today, months=MONTHS):
    """USD received in each of the last few months, oldest first, the current month last."""
    first = month_start(today)
    for _ in range(months - 1):
        first = month_start(first - datetime.timedelta(days=1))
    rows, month = [], first
    while month <= today:
        begin, finish = _period_bounds(month, next_month(month) - datetime.timedelta(days=1))
        total = Payment.objects.filter(status=Payment.PAID, paid_at__gte=begin, paid_at__lt=finish).exclude(
            method__in=Payment.NOT_RECEIVED).aggregate(t=Sum("amount_usd"))["t"]
        rows.append({"month": month.isoformat()[:7], "amount": total or ZERO})
        month = next_month(month)
    return rows


def repairs_by_status():
    """Open complaints or repairs, counted by status, biggest first."""
    rows = (
        Complain.objects.filter(status=True)
        .values("compalint_status__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    return [{"status": r["compalint_status__name"] or "No status", "count": r["count"]} for r in rows]


def recent_repairs(limit=5):
    rows = (
        Complain.objects.filter(status=True)
        .exclude(compalint_status__name__iregex=CLOSED_REPAIR)
        .select_related("complaint_category", "compalint_status")
        .order_by("-date_created")[:limit]
    )
    return [
        {"id": c.id, "home": c.home, "stand": c.stand_number, "category": c.complaint_category.name,
         "status": c.compalint_status.name, "created": c.date_created}
        for c in rows
    ]


class EstateDashboard(APIView):
    """GET /dashboard: the home page of the estate the user is working in."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request):
        estate = current_estate()
        if estate is None or estate is ALL:
            return Response({"detail": "Choose an estate first."}, status=400)
        today = timezone.localdate()
        data = {"estate": estate_row(estate), "today": today, "bill_word": estate.bill_word}
        if not estate.is_rental:
            data["gate"] = gate_today(today)
        if not is_admin(request.user):
            return Response(data)

        data["summary"] = summarise(estate, today)
        data["collected_by_month"] = collected_by_month(today)
        data["repairs_by_status"] = repairs_by_status()
        data["recent_repairs"] = recent_repairs()
        data["counts"] = {
            "stands": Stand.objects.count(),
            "homes": Home.objects.count(),
            "residents": Resident.objects.filter(status=True).count(),
            "providers": Provider.objects.count(),
        }
        return Response(data)
