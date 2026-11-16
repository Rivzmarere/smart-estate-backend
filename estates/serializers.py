from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Estate

SECRET_FIELDS = ["paynow_usd_integration_key", "paynow_zwg_integration_key"]


class EstateSerializer(serializers.ModelSerializer):
    """Integration keys are write-only; reads say whether one is set."""

    paynow_usd_ready = serializers.SerializerMethodField()
    paynow_zwg_ready = serializers.SerializerMethodField()
    homes = serializers.SerializerMethodField()
    staff = serializers.SerializerMethodField()

    class Meta:
        model = Estate
        fields = [
            "id", "name", "slug", "active", "sandbox", "address", "office_phone", "office_hours", "emergency_phones", "household_approval",
            "paynow_usd_integration_id", "paynow_usd_integration_key", "paynow_zwg_integration_id",
            "paynow_zwg_integration_key", "paynow_auth_email", "paynow_usd_ready", "paynow_zwg_ready",
            "homes", "staff", "created_at",
        ]
        extra_kwargs = {**{name: {"write_only": True, "required": False} for name in SECRET_FIELDS}, "slug": {"required": False}}

    def get_paynow_usd_ready(self, estate):
        return bool(estate.paynow_usd_integration_id and estate.paynow_usd_integration_key)

    def get_paynow_zwg_ready(self, estate):
        return bool(estate.paynow_zwg_integration_id and estate.paynow_zwg_integration_key)

    def get_homes(self, estate):
        from home.models import Home

        return Home.all_estates.filter(estate=estate, status=True).count()

    def get_staff(self, estate):
        return estate.users.filter(is_active=True).count()

    def update(self, instance, validated):
        # An empty key in the form means "keep the current one".
        for name in SECRET_FIELDS:
            if validated.get(name) == "":
                validated.pop(name)
        return super().update(instance, validated)


class EstateSettingsSerializer(EstateSerializer):
    """What an estate's own administrator may change (not the slug or active flag)."""

    class Meta(EstateSerializer.Meta):
        read_only_fields = ["slug", "active", "sandbox", "created_at"]


class FirstAdminSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=45)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        from authentication.models import User

        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value
