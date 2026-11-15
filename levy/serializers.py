from datetime import date
from decimal import Decimal

from rest_framework import serializers

from .models import ExchangeRate, Invoice, Payment


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = ["id", "effective_from", "zig_per_usd", "note", "created_at"]

    def validate_zig_per_usd(self, value):
        if value <= 0:
            raise serializers.ValidationError("The rate must be more than zero.")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "home", "stand_number", "address", "kind", "kind_label", "period", "description",
            "amount_usd", "issued_on", "due_date", "void", "void_reason", "created_at",
        ]
        read_only_fields = ["number", "stand_number", "address", "void", "void_reason", "created_at"]

    def validate_home(self, home):
        if not home.status:
            raise serializers.ValidationError("That home is not active.")
        return home

    def validate_amount_usd(self, value):
        if value <= 0:
            raise serializers.ValidationError("The amount must be more than zero.")
        return value

    def validate(self, attrs):
        if attrs.get("kind", Invoice.LEVY) == Invoice.LEVY:
            period = attrs.get("period")
            if not period:
                raise serializers.ValidationError({"period": "A monthly levy needs the month it is for."})
            attrs["period"] = period.replace(day=1)
            exists = Invoice.objects.filter(home=attrs["home"], period=attrs["period"], kind=Invoice.LEVY, void=False)
            if self.instance:
                exists = exists.exclude(pk=self.instance.pk)
            if exists.exists():
                raise serializers.ValidationError({"period": "This home already has a levy for that month."})
        return attrs

    def create(self, validated):
        home = validated["home"]
        validated["stand_number"] = home.stand.stand_number
        validated["address"] = home.address
        return super().create(validated)


class GenerateSerializer(serializers.Serializer):
    period = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", help_text="YYYY-MM")
    amount_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    due_date = serializers.DateField()
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    preview = serializers.BooleanField(default=False)

    def validate_period(self, value):
        year, month = map(int, value.split("-"))
        return date(year, month, 1)


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class PaymentSerializer(serializers.ModelSerializer):
    """Office payments (cash, bank transfer, a mobile-money transfer seen on a statement)."""

    method_label = serializers.CharField(source="get_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    stand_number = serializers.IntegerField(source="home.stand.stand_number", read_only=True)
    address = serializers.CharField(source="home.address", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    exchange_rate = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, allow_null=True)

    class Meta:
        model = Payment
        fields = [
            "id", "home", "stand_number", "address", "currency", "amount", "exchange_rate", "amount_usd", "method",
            "method_label", "status", "status_label", "channel", "reference", "note", "receipt_number", "phone",
            "paynow_reference", "failure_reason", "recorded_by_name", "created_at", "paid_at",
        ]
        read_only_fields = [
            "amount_usd", "status", "channel", "receipt_number", "phone", "paynow_reference", "failure_reason",
            "created_at", "paid_at",
        ]

    def get_recorded_by_name(self, payment):
        user = payment.recorded_by
        return (user.get_full_name() or user.username) if user else ""

    def validate_home(self, home):
        if not home.status:
            raise serializers.ValidationError("That home is not active.")
        return home

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("The amount must be more than zero.")
        return value

    def validate(self, attrs):
        from .accounts import to_usd

        currency = attrs.get("currency", Payment.USD)
        if currency == Payment.ZWG:
            rate = attrs.get("exchange_rate")
            if not rate:
                current = ExchangeRate.on()
                if current is None:
                    raise serializers.ValidationError({"exchange_rate": "Set today's ZiG rate first, or type the rate used."})
                rate = current.zig_per_usd
            if rate <= 0:
                raise serializers.ValidationError({"exchange_rate": "The rate must be more than zero."})
            attrs["exchange_rate"] = rate
        else:
            attrs["exchange_rate"] = None
        attrs["amount_usd"] = to_usd(attrs["amount"], currency, attrs["exchange_rate"])
        return attrs

