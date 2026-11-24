"""
Daily gate report: everything that happened at the gate on one day (Harare time).
"""

from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from complaint.models import Complain
from smartEstateBackend.permissions import IsAdminRole
from visit.models import Visit
from whitelist.models import WhiteList


def day_bounds(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def local(dt):
    return timezone.localtime(dt).isoformat() if dt else None


def guard_name(user):
    if not user:
        return ""
    return user.get_full_name() or user.username


class GateDailyReport(APIView):
    """GET /reports/gate-daily?date=YYYY-MM-DD (default: today)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        raw = request.query_params.get("date")
        try:
            day = date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            return Response({"date": "Use the format YYYY-MM-DD."}, status=400)
        start, end = day_bounds(day)

        def within(field):
            return Q(**{f"{field}__gte": start, f"{field}__lt": end})

        visits = list(
            Visit.objects.filter(within("date_created") | within("date_arrived") | within("date_depature"))
            .select_related("transport_type", "visit_status", "authorized_by")
            .order_by("date_arrived", "date_created")
        )
        booked = [v for v in visits if start <= v.date_created < end]
        arrived = [v for v in visits if v.date_arrived and start <= v.date_arrived < end]
        departed = [v for v in visits if v.date_depature and start <= v.date_depature < end]
        still_inside = [v for v in visits if v.date_arrived and v.date_arrived < end and (not v.date_depature or v.date_depature >= end)]
        cancelled = [v for v in booked if not v.status and not v.date_arrived]
        no_show = [v for v in booked if v.status and not v.date_arrived]

        arrivals_by_hour = [0] * 24
        for v in arrived:
            arrivals_by_hour[timezone.localtime(v.date_arrived).hour] += 1

        whitelist = list(
            WhiteList.objects.filter(within("date_arrived")).select_related("white_list_guest", "authorized_by").order_by("date_arrived")
        )
        complaints = Complain.objects.filter(within("date_created")).count()

        def visit_row(v):
            if v.date_depature:
                state = "Left"
            elif v.date_arrived:
                state = "Inside"
            elif not v.status:
                state = "Cancelled"
            else:
                state = "Expected"
            return {
                "id": v.id,
                "visit_code": v.visit_code,
                "visitor_name": v.visitor_name,
                "visitor_national_id": v.visitor_national_id,
                "vehicle": v.visitor_vehicle_reg_number or "",
                "transport": v.transport_type.name if v.transport_type_id else "",
                "stand_number": v.stand_number,
                "home": v.home,
                "booked_at": local(v.date_created),
                "arrived_at": local(v.date_arrived),
                "departed_at": local(v.date_depature),
                "booked_in_by": guard_name(v.authorized_by),
                "state": state,
            }

        return Response({
            "date": day.isoformat(),
            "generated_at": local(timezone.now()),
            "totals": {
                "booked": len(booked),
                "arrived": len(arrived),
                "departed": len(departed),
                "still_inside": len(still_inside),
                "no_show": len(no_show),
                "cancelled": len(cancelled),
                "whitelist_entries": len(whitelist),
                "complaints": complaints,
            },
            "arrivals_by_hour": arrivals_by_hour,
            "visits": [visit_row(v) for v in visits],
            "whitelist": [
                {
                    "visitor_name": w.white_list_guest.visitor_name,
                    "stand_number": w.white_list_guest.stand_number,
                    "arrived_at": local(w.date_arrived),
                    "booked_in_by": guard_name(w.authorized_by),
                }
                for w in whitelist
            ],
        })
