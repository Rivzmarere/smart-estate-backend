"""GET audit?area=money&search=receipt&page=2 : the estate's history, newest first (administrators)."""

from rest_framework import serializers
from rest_framework.views import APIView

from estates.context import ALL, current_estate
from smartEstateBackend.listing import page, param, search
from smartEstateBackend.permissions import IsAdminRole

from .models import AuditEntry


class AuditRowSerializer(serializers.ModelSerializer):
    area_label = serializers.CharField(source="get_area_display", read_only=True)
    estate_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEntry
        fields = ["id", "at", "who", "area", "area_label", "action", "summary", "object_type", "object_id", "estate_name"]

    def get_estate_name(self, row):
        return row.estate.name if row.estate_id else ""


class History(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        estate = current_estate()
        rows = AuditEntry.objects.select_related("estate")
        if estate is None:
            rows = rows.none()
        elif estate is not ALL:
            rows = rows.filter(estate=estate)
        area = param(request, "area")
        if area:
            rows = rows.filter(area=area)
        if param(request, "search"):
            rows = search(rows, param(request, "search"), ["summary", "who"])
        return page(request, rows, AuditRowSerializer, per_page=50)
