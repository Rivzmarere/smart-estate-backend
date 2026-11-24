"""
Endpoints for the guard's gate screen.

The gate tablet keeps a copy of the expected-visitor list and queues
book-in / book-out actions while offline, replaying them later. So:
  * actions carry the time they really happened (``at``), within limits;
  * replaying the same action twice is harmless (idempotent).
"""

from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from parameters.models.models_visit_status import VisitStatus
from smartEstateBackend.permissions import IsAdminOrGuard

from .messaging import notify_visitor_arrived
from .models import Visit

EXPECTED_WINDOW = timedelta(days=7)
MAX_OFFLINE_AGE = timedelta(hours=48)
CLOCK_SKEW = timedelta(minutes=5)


def status_named(*names):
    for name in names:
        found = VisitStatus.objects.filter(name__iexact=name).first()
        if found:
            return found
    return None


def event_time(raw):
    """The time an action happened: the tablet's timestamp if sane, else now."""
    now = timezone.now()
    if not raw:
        return now
    when = parse_datetime(str(raw))
    if when is None:
        raise serializers.ValidationError({"at": "Invalid date-time."})
    if timezone.is_naive(when):
        when = timezone.make_aware(when)
    if when > now + CLOCK_SKEW:
        raise serializers.ValidationError({"at": "Time is in the future; check the tablet's clock."})
    if when < now - MAX_OFFLINE_AGE:
        raise serializers.ValidationError({"at": "Too old to sync; enter it manually."})
    return min(when, now)


class GateVisitSerializer(serializers.ModelSerializer):
    transport = serializers.CharField(source="transport_type.name", read_only=True)
    visit_status_name = serializers.CharField(source="visit_status.name", read_only=True)

    class Meta:
        model = Visit
        fields = [
            "id", "visit_code", "visitor_name", "visitor_vehicle_reg_number", "stand_number", "home",
            "transport", "visit_status_name", "date_created", "date_arrived", "date_depature", "status",
        ]


class GateExpected(APIView):
    """Visitors booked in the last 7 days who have not yet left."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request):
        visits = (
            Visit.objects.filter(status=True, date_created__gte=timezone.now() - EXPECTED_WINDOW)
            .select_related("transport_type", "visit_status")
            .order_by("-date_created")[:500]
        )
        return Response({"data": GateVisitSerializer(visits, many=True).data, "server_time": timezone.now()})


class GateBookIn(APIView):
    permission_classes = [IsAdminOrGuard]

    def post(self, request, id):
        visit = get_object_or_404(Visit, pk=id)
        if visit.date_arrived:
            return Response({"data": GateVisitSerializer(visit).data, "already": True})
        if not visit.status:
            return Response({"errors": "This booking was cancelled."}, status=status.HTTP_409_CONFLICT)
        national_id = " ".join(str(request.data.get("visitor_national_id", "")).split()).upper()
        if len(national_id) < 4:
            return Response({"visitor_national_id": "Enter the visitor's ID number."}, status=status.HTTP_400_BAD_REQUEST)
        visit.date_arrived = event_time(request.data.get("at"))
        visit.visitor_national_id = national_id[:25]
        visit.authorized_by = request.user
        visit.visit_status = status_named("Inside", "Arrived") or visit.visit_status
        visit.save()
        notify_visitor_arrived(visit)
        return Response({"data": GateVisitSerializer(visit).data, "already": False}, status=status.HTTP_201_CREATED)


class GateBookOut(APIView):
    permission_classes = [IsAdminOrGuard]

    def post(self, request, id):
        visit = get_object_or_404(Visit, pk=id)
        if visit.date_depature:
            return Response({"data": GateVisitSerializer(visit).data, "already": True})
        when = event_time(request.data.get("at"))
        if visit.date_arrived and when < visit.date_arrived:
            when = visit.date_arrived
        visit.date_depature = when
        visit.status = False
        visit.visit_status = status_named("Departed", "Left") or visit.visit_status
        visit.save()
        return Response({"data": GateVisitSerializer(visit).data, "already": False}, status=status.HTTP_201_CREATED)
