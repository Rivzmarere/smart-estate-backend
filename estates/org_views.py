"""
Managing agents and landlords: one account, many estates or rental portfolios.

Platform staff create the organisation and its first login. The
organisation's own staff then add estates, portfolios and colleagues, and
see everything they run on one screen.
"""

from django.contrib.auth.password_validation import validate_password
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User
from smartEstateBackend.permissions import ROLE_ADMIN, ROLES, is_admin

from .context import use_estate
from .models import Estate, Organisation
from .views import IsPlatformStaff

CLOSED_REPAIR = r"^(resolved|closed|done|completed)$"


def is_platform(user):
    return bool(user and user.is_authenticated and user.is_superuser and not user.estate_id)


class IsOrganisationManager(BasePermission):
    """An administrator working for a managing agent or landlord across its estates."""

    message = "Only the administrators of a managing agent or landlord account can do this."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.spans_organisation and is_admin(user) and user.organisation.active)


def unit_count(organisation):
    from home.models import Home

    return Home.all_estates.filter(estate__organisation=organisation, estate__active=True, estate__sandbox=False, status=True).count()


class OrganisationSerializer(serializers.ModelSerializer):
    estates = serializers.SerializerMethodField()
    units = serializers.SerializerMethodField()
    staff = serializers.SerializerMethodField()
    monthly_usd = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        fields = ["id", "name", "kind", "active", "contact_name", "phone", "email", "price_per_unit_usd", "estates", "units",
                  "staff", "monthly_usd", "created_at"]

    def get_estates(self, organisation):
        return organisation.estates.filter(active=True).count()

    def get_units(self, organisation):
        return unit_count(organisation)

    def get_staff(self, organisation):
        return organisation.users.filter(is_active=True).count()

    def get_monthly_usd(self, organisation):
        return unit_count(organisation) * organisation.price_per_unit_usd


class NewLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=45)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=ROLES, default=ROLE_ADMIN)
    estate = serializers.IntegerField(required=False, allow_null=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


class NewEstateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Estate
        fields = ["name", "kind", "address", "office_phone", "office_hours", "management_fee_percent"]


# ---------------------------------------------------------------- platform staff

class Organisations(generics.ListCreateAPIView):
    permission_classes = [IsPlatformStaff]
    serializer_class = OrganisationSerializer
    pagination_class = None
    queryset = Organisation.objects.all()


class OrganisationDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [IsPlatformStaff]
    serializer_class = OrganisationSerializer
    lookup_url_kwarg = "id"
    queryset = Organisation.objects.all()


class OrganisationFirstAdmin(APIView):
    """A login for the agent or landlord, who then adds their own estates and colleagues."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, id):
        organisation = get_object_or_404(Organisation, pk=id)
        serializer = NewLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create_user(
            username=data["username"], password=data["password"], role=ROLE_ADMIN, organisation=organisation,
            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
        )
        return Response({"id": user.id, "username": user.username, "organisation": organisation.name}, status=201)


# ---------------------------------------------------------------- the organisation's own staff

def estate_row(estate):
    return {"id": estate.id, "name": estate.name, "slug": estate.slug, "kind": estate.kind, "sandbox": estate.sandbox,
            "address": estate.address}


class MyOrganisation(APIView):
    """Who I work for and the estates I can switch between."""

    permission_classes = [IsOrganisationManager]

    def get(self, request):
        organisation = request.user.organisation
        estates = organisation.estates.filter(active=True)
        return Response({
            "id": organisation.id, "name": organisation.name, "kind": organisation.kind,
            "estates": [estate_row(e) for e in estates],
        })


class MyEstates(APIView):
    """Add an estate or a rental portfolio to my organisation."""

    permission_classes = [IsOrganisationManager]

    def post(self, request):
        serializer = NewEstateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        estate = serializer.save(organisation=request.user.organisation)
        return Response(estate_row(estate), status=201)


def summarise(estate, today):
    """The numbers an agent or landlord watches, for one estate or portfolio."""
    from assist.models import EmergencyAlert
    from complaint.models import Complain
    from levy.accounts import ZERO, all_accounts
    from portal.models import HouseholdRequest
    from rentals import services as rentals

    with use_estate(estate):
        row = {**estate_row(estate), "leases_ending": 0, "vacant": 0}
        if estate.is_rental:
            _, totals = rentals.rent_roll(today)
            row.update(units=totals["properties"], occupied=totals["let"], vacant=totals["vacant"], arrears=totals["arrears"],
                       in_arrears=totals["tenants_in_arrears"], collected_this_month=totals["collected_this_month"],
                       monthly_rent=totals["monthly_rent"], leases_ending=totals["leases_ending"])
        else:
            accounts = all_accounts(today)
            collected = rentals.collected_between(rentals.month_start(today), rentals.month_end(today))
            row.update(units=len(accounts), occupied=sum(1 for a in accounts if a["resident"]),
                       arrears=sum((a["arrears"] for a in accounts), ZERO), in_arrears=sum(1 for a in accounts if a["arrears"] > 0),
                       collected_this_month=sum(collected.values(), ZERO), monthly_rent=None)
        row["open_repairs"] = Complain.objects.filter(status=True).exclude(compalint_status__name__iregex=CLOSED_REPAIR).count()
        row["emergencies"] = EmergencyAlert.objects.exclude(status=EmergencyAlert.RESOLVED).count()
        row["household_requests"] = HouseholdRequest.objects.filter(status=HouseholdRequest.PENDING).count()
    return row


class Overview(APIView):
    """Every estate and portfolio of the organisation on one screen."""

    permission_classes = [IsOrganisationManager]

    def get(self, request):
        from levy.accounts import ZERO

        organisation = request.user.organisation
        today = timezone.localdate()
        rows = [summarise(estate, today) for estate in organisation.estates.filter(active=True)]
        totals = {
            "estates": len(rows),
            "units": sum(r["units"] for r in rows),
            "occupied": sum(r["occupied"] for r in rows),
            "arrears": sum((r["arrears"] for r in rows), ZERO),
            "in_arrears": sum(r["in_arrears"] for r in rows),
            "collected_this_month": sum((r["collected_this_month"] for r in rows), ZERO),
            "open_repairs": sum(r["open_repairs"] for r in rows),
            "emergencies": sum(r["emergencies"] for r in rows),
            "leases_ending": sum(r["leases_ending"] for r in rows),
        }
        return Response({"organisation": {"name": organisation.name, "kind": organisation.kind}, "totals": totals, "estates": rows})


class Staff(APIView):
    """Colleagues: across the whole organisation, or tied to one of its estates (office staff, guards)."""

    permission_classes = [IsOrganisationManager]

    def get(self, request):
        organisation = request.user.organisation
        users = (User.objects.filter(organisation=organisation) | User.objects.filter(estate__organisation=organisation)).select_related("estate")
        return Response([
            {"id": u.id, "username": u.username, "name": u.get_full_name(), "role": u.role, "active": u.is_active,
             "estate": u.estate.name if u.estate_id else None}
            for u in users.order_by("estate__name", "username")
        ])

    def post(self, request):
        organisation = request.user.organisation
        serializer = NewLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        estate = None
        if data.get("estate"):
            estate = organisation.estates.filter(pk=data["estate"]).first()
            if estate is None:
                return Response({"estate": "That estate is not one of yours."}, status=400)
        elif data["role"] != ROLE_ADMIN:
            return Response({"estate": "Choose the estate this guard works at."}, status=400)
        user = User.objects.create_user(
            username=data["username"], password=data["password"], role=data["role"],
            estate=estate, organisation=None if estate else organisation,
            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
        )
        return Response({"id": user.id, "username": user.username, "role": user.role, "estate": estate.name if estate else None}, status=201)
