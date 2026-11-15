from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User
from smartEstateBackend.permissions import ROLE_ADMIN, IsAdminRole

from .context import ALL, current_estate
from .models import Estate
from .serializers import EstateSerializer, EstateSettingsSerializer, FirstAdminSerializer


class IsPlatformStaff(BasePermission):
    """Runs the service for every estate: a superuser not tied to one estate."""

    message = "Only platform staff can manage estates."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser and not user.estate_id)


class Estates(generics.ListCreateAPIView):
    permission_classes = [IsPlatformStaff]
    serializer_class = EstateSerializer
    pagination_class = None

    def get_queryset(self):
        return Estate.objects.all()


class EstateDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [IsPlatformStaff]
    serializer_class = EstateSerializer
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return Estate.objects.all()


class EstateFirstAdmin(APIView):
    """Create an administrator for an estate (who then adds the rest of the staff)."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, id):
        estate = get_object_or_404(Estate, pk=id)
        serializer = FirstAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create_user(
            username=data["username"], password=data["password"], role=ROLE_ADMIN, estate=estate,
            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
        )
        return Response({"id": user.id, "username": user.username, "estate": estate.slug}, status=201)


class MyEstate(APIView):
    """The administrator's own estate settings."""

    permission_classes = [IsAdminRole]

    def _estate(self):
        estate = current_estate()
        return None if estate is ALL else estate

    def get(self, request):
        estate = self._estate()
        if estate is None:
            return Response({"detail": "Choose an estate first."}, status=400)
        return Response(EstateSettingsSerializer(estate).data)

    def put(self, request):
        estate = self._estate()
        if estate is None:
            return Response({"detail": "Choose an estate first."}, status=400)
        serializer = EstateSettingsSerializer(estate, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PublicEstate(APIView):
    """Name and contact details for the resident portal (?estate=<slug>)."""

    permission_classes = [AllowAny]

    def get(self, request):
        estate = current_estate()
        if estate is None or estate is ALL:
            return Response({"detail": "Unknown estate."}, status=404)
        whatsapp = settings.WHATSAPP_PUBLIC_NUMBER if settings.WHATSAPP_ENABLED else ""
        return Response({
            "name": estate.name, "slug": estate.slug, "address": estate.address,
            "office_phone": estate.office_phone, "office_hours": estate.office_hours,
            "whatsapp_number": "".join(ch for ch in whatsapp if ch.isdigit()),
        })
