from decimal import Decimal

from rest_framework import serializers

from home.models import Home
from owner.models import Owner
from resident.models import Resident
from sms.sender import zimbabwe_mobile

from .models import Expense, Lease


def local(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return "0" + digits[3:] if digits.startswith("263") else digits


def mobile(value):
    phone = zimbabwe_mobile(value)
    if not phone:
        raise serializers.ValidationError("Enter a Zimbabwean mobile number, e.g. 0772 123 456.")
    return local(phone)


class PropertySerializer(serializers.Serializer):
    """A property to let: its address, and whose it is (an owner already on file, or a new one)."""

    address = serializers.CharField(max_length=200)
    reference = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=Owner.all_estates.none(), required=False, allow_null=True)
    owner_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    owner_surname = serializers.CharField(max_length=60, required=False, allow_blank=True)
    owner_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = Owner.objects.filter(status=True)

    def validate(self, attrs):
        if not attrs.get("owner") and not self.partial:
            if not (attrs.get("owner_name") and attrs.get("owner_surname") and attrs.get("owner_phone")):
                raise serializers.ValidationError({"owner": "Choose the owner, or give the new owner's name, surname and mobile number."})
        if attrs.get("owner_phone"):
            attrs["owner_phone"] = mobile(attrs["owner_phone"])
        return attrs


class LeaseSerializer(serializers.ModelSerializer):
    tenant_name = serializers.SerializerMethodField()
    tenant_phone = serializers.CharField(source="tenant.phone_number1", read_only=True)
    address = serializers.CharField(source="home.address", read_only=True)
    reference = serializers.IntegerField(source="home.stand.stand_number", read_only=True)
    deposit_held_usd = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    has_document = serializers.SerializerMethodField()

    class Meta:
        model = Lease
        fields = [
            "id", "home", "address", "reference", "tenant", "tenant_name", "tenant_phone", "start_date", "end_date", "rent_usd",
            "due_day", "deposit_usd", "deposit_paid_usd", "deposit_held_usd", "status", "notes", "ended_on", "end_reason",
            "deposit_returned_usd", "deposit_deducted_usd", "has_document", "document_name", "created_at",
        ]
        read_only_fields = [
            "home", "tenant", "status", "ended_on", "end_reason", "deposit_returned_usd", "deposit_deducted_usd",
            "document_name", "created_at",
        ]

    def get_tenant_name(self, lease):
        return f"{lease.tenant.name} {lease.tenant.surname}".strip()

    def get_has_document(self, lease):
        return bool(lease.document)

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "The lease cannot end before it starts."})
        return attrs


class StartLeaseSerializer(serializers.Serializer):
    """A new lease for a property: an existing tenant on file, or a new person."""

    home = serializers.PrimaryKeyRelatedField(queryset=Home.all_estates.none())
    tenant = serializers.PrimaryKeyRelatedField(queryset=Resident.all_estates.none(), required=False, allow_null=True)
    tenant_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    tenant_surname = serializers.CharField(max_length=60, required=False, allow_blank=True)
    tenant_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    tenant_id_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    rent_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    due_day = serializers.IntegerField(min_value=1, max_value=28, default=1)
    deposit_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    deposit_paid_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    first_rent_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["home"].queryset = Home.objects.filter(status=True)
        self.fields["tenant"].queryset = Resident.objects.filter(status=True)

    def validate(self, attrs):
        if not attrs.get("tenant"):
            if not (attrs.get("tenant_name") and attrs.get("tenant_surname") and attrs.get("tenant_phone")):
                raise serializers.ValidationError({"tenant": "Choose the tenant, or give the new tenant's name, surname and mobile number."})
            attrs["tenant_phone"] = mobile(attrs["tenant_phone"])
        if attrs.get("end_date") and attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "The lease cannot end before it starts."})
        return attrs


class EndLeaseSerializer(serializers.Serializer):
    ended_on = serializers.DateField()
    deposit_returned_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    deposit_deducted_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


class BillSerializer(serializers.Serializer):
    period = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", help_text="YYYY-MM")
    preview = serializers.BooleanField(default=False)


class ExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    address = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = ["id", "home", "address", "date", "category", "category_label", "description", "amount_usd", "paid_to", "created_at"]

    def get_address(self, expense):
        return expense.home.address if expense.home_id else "Whole portfolio"
