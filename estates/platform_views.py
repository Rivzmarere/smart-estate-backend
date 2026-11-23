"""
GET platform/usage: how each estate is using Smart Estate (platform staff only).

For spotting estates that stopped using it, and for billing: homes count,
staff activity, money and visitors in the last 30 days.
"""

import datetime

from django.db.models import Count, Max, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User

from .context import use_estate
from .models import Estate
from .views import IsPlatformStaff

WINDOW = datetime.timedelta(days=30)


def usage(estate, since):
    from audit.models import AuditEntry
    from home.models import Home
    from levy.models import Payment
    from visit.models import Visit

    with use_estate(estate):
        homes = Home.objects.filter(status=True).count()
        occupied = Home.objects.filter(status=True, resident__isnull=False).count()
        paid = Payment.objects.filter(status=Payment.PAID, paid_at__gte=since).exclude(method__in=Payment.NOT_RECEIVED)
        money = paid.aggregate(n=Count("id"), usd=Sum("amount_usd"))
        online = paid.exclude(channel=Payment.OFFICE).count()
        visits = Visit.objects.filter(date_created__gte=since).count()
    staff = User.objects.filter(estate=estate)
    org = estate.organisation
    price = org.price_per_unit_usd if org else None
    last_activity = AuditEntry.objects.filter(estate=estate).aggregate(at=Max("at"))["at"]
    last_login = staff.aggregate(at=Max("last_login"))["at"]
    return {
        "id": estate.id, "name": estate.name, "slug": estate.slug, "kind": estate.kind, "active": estate.active, "sandbox": estate.sandbox,
        "organisation": org.name if org else "",
        "homes": homes, "occupied": occupied,
        "staff": staff.filter(is_active=True).count(),
        "staff_active_30d": staff.filter(is_active=True, last_login__gte=since).count(),
        "last_sign_in": last_login,
        "last_activity": max(filter(None, [last_activity, last_login]), default=None),
        "payments_30d": money["n"] or 0, "collected_30d": money["usd"] or 0, "paid_online_30d": online,
        "visitors_30d": visits,
        "price_per_unit_usd": price, "monthly_bill_usd": (price * homes) if price else None,
        "created_at": estate.created_at,
    }


class PlatformUsage(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        since = timezone.now() - WINDOW
        rows = [usage(e, since) for e in Estate.objects.select_related("organisation").order_by("sandbox", "name")]
        live = [r for r in rows if r["active"] and not r["sandbox"]]
        totals = {
            "estates": len(live),
            "homes": sum(r["homes"] for r in live),
            "monthly_bill_usd": sum((r["monthly_bill_usd"] or 0) for r in live),
            "quiet": sum(1 for r in live if not r["last_activity"] or r["last_activity"] < since),
        }
        return Response({"totals": totals, "estates": rows})
