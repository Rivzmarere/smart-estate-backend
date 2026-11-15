from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from home.models import Home
from parameters.models.models_transport_type import TransportType
from smartEstateBackend.permissions import IsAdminOrGuard

from .models import WalkInRequest
from .services import answer, ask_resident


class WalkInCreateSerializer(serializers.Serializer):
    stand_number = serializers.IntegerField()
    visitor_name = serializers.CharField(max_length=60, min_length=2)
    visitor_national_id = serializers.CharField(max_length=20, required=False, allow_blank=True)
    vehicle = serializers.CharField(max_length=20, required=False, allow_blank=True)
    transport_type = serializers.PrimaryKeyRelatedField(queryset=TransportType.objects.filter(status=True), required=False, allow_null=True)


class WalkInSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    visit_code = serializers.CharField(source="visit.visit_code", read_only=True, default=None)
    expires_at = serializers.DateTimeField(read_only=True)
    resident_name = serializers.SerializerMethodField()

    class Meta:
        model = WalkInRequest
        fields = [
            "id", "stand_number", "address", "resident_name", "resident_phone", "visitor_name", "visitor_national_id",
            "vehicle", "status", "status_label", "whatsapp_sent", "answered_via", "answered_at", "visit", "visit_code",
            "created_at", "expires_at",
        ]

    def get_resident_name(self, walk_in):
        resident = walk_in.home.resident
        return f"{resident.name} {resident.surname}" if resident else ""


def _rows(queryset):
    rows = list(queryset.select_related("home__resident", "visit"))
    for row in rows:
        row.expire_if_stale()
    return rows


class WalkIns(APIView):
    """GET today's walk-in requests; POST asks a resident to approve a visitor at the gate."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request):
        today = timezone.localdate()
        rows = _rows(WalkInRequest.objects.filter(created_at__date=today)[:100])
        return Response(WalkInSerializer(rows, many=True).data)

    def post(self, request):
        serializer = WalkInCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        home = (
            Home.objects.filter(stand__stand_number=data["stand_number"], status=True)
            .select_related("resident", "stand").order_by("id").first()
        )
        if home is None:
            return Response({"stand_number": "No active home on that stand."}, status=400)
        phone = (home.resident.phone_number1 or "") if home.resident else ""
        walk_in = WalkInRequest.objects.create(
            home=home,
            stand_number=home.stand.stand_number,
            address=home.address,
            resident_phone=phone,
            visitor_name=" ".join(data["visitor_name"].split()),
            visitor_national_id=data.get("visitor_national_id", ""),
            vehicle="".join((data.get("vehicle") or "").upper().split()),
            transport_type=data.get("transport_type"),
            requested_by=request.user,
        )
        if phone:
            ask_resident(walk_in)
        return Response(WalkInSerializer(walk_in).data, status=201)


class WalkInDetail(APIView):
    """The gate polls this until the resident answers."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request, id):
        walk_in = get_object_or_404(WalkInRequest.objects.select_related("home__resident", "visit"), pk=id)
        walk_in.expire_if_stale()
        return Response(WalkInSerializer(walk_in).data)


class WalkInDecide(APIView):
    """The guard records an answer the resident gave by phone: {"approve": true|false}."""

    permission_classes = [IsAdminOrGuard]

    def post(self, request, id):
        approve = request.data.get("approve")
        if not isinstance(approve, bool):
            return Response({"approve": "Send true or false."}, status=400)
        walk_in, changed = answer(id, approve, WalkInRequest.PHONE_CALL)
        if walk_in is None:
            return Response(status=404)
        if not changed:
            return Response({"detail": f"This request is already {walk_in.get_status_display().lower()}."}, status=409)
        walk_in.refresh_from_db()
        return Response(WalkInSerializer(walk_in).data)
