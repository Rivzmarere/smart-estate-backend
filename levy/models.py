"""
Estate levies: invoices per home in US dollars, paid in USD or ZiG.

Invoices are always in USD, the way Zimbabwean estates bill. A payment in
ZiG is converted at the exchange rate recorded with it, so the account
balance is always in USD.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from authentication.models import User
from home.models import Home

CENTS = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


class ExchangeRate(models.Model):
    """ZiG per US dollar from a given day (the estate's chosen rate, e.g. the RBZ interbank rate)."""

    effective_from = models.DateField(unique=True)
    zig_per_usd = models.DecimalField(max_digits=12, decimal_places=4)
    note = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    @classmethod
    def on(cls, day=None):
        """The rate in force on `day` (default today), or None."""
        day = day or timezone.localdate()
        return cls.objects.filter(effective_from__lte=day).order_by("-effective_from").first()

    def __str__(self):
        return f"ZiG {self.zig_per_usd} per USD from {self.effective_from}"


class Invoice(models.Model):
    LEVY = "levy"
    SPECIAL = "special"
    PENALTY = "penalty"
    OTHER = "other"
    KINDS = [(LEVY, "Monthly levy"), (SPECIAL, "Special levy"), (PENALTY, "Penalty"), (OTHER, "Other")]

    number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    home = models.ForeignKey(Home, on_delete=models.PROTECT, related_name="invoices")
    stand_number = models.IntegerField()
    address = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=KINDS, default=LEVY)
    period = models.DateField(null=True, blank=True, help_text="First day of the month billed (monthly levies)")
    description = models.CharField(max_length=200)
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    issued_on = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    void = models.BooleanField(default=False)
    void_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["home", "period"],
                condition=models.Q(kind="levy", void=False),
                name="one_monthly_levy_per_home_per_month",
            )
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"INV{self.issued_on:%y%m}-{self.pk:05d}"
            super().save(update_fields=["number"])

    def __str__(self):
        return f"{self.number} {self.address} USD {self.amount_usd}"


class Payment(models.Model):
    USD = "USD"
    ZWG = "ZWG"
    CURRENCIES = [(USD, "US dollar"), (ZWG, "ZiG")]

    CASH = "cash"
    BANK = "bank"
    ECOCASH = "ecocash"
    ONEMONEY = "onemoney"
    INNBUCKS = "innbucks"
    CARD = "card"
    METHODS = [
        (CASH, "Cash"),
        (BANK, "Bank transfer"),
        (ECOCASH, "EcoCash"),
        (ONEMONEY, "OneMoney"),
        (INNBUCKS, "InnBucks"),
        (CARD, "Card"),
    ]
    MOBILE_METHODS = {ECOCASH, ONEMONEY, INNBUCKS}

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STATUSES = [(PENDING, "Waiting for approval"), (PAID, "Paid"), (FAILED, "Failed"), (CANCELLED, "Cancelled")]

    OFFICE = "office"
    WHATSAPP = "whatsapp"
    CHANNELS = [(OFFICE, "Estate office"), (WHATSAPP, "WhatsApp")]

    home = models.ForeignKey(Home, on_delete=models.PROTECT, related_name="payments")
    currency = models.CharField(max_length=3, choices=CURRENCIES, default=USD)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="In the payment currency")
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, help_text="ZiG per USD, for ZiG payments")
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS)
    status = models.CharField(max_length=10, choices=STATUSES, default=PAID)
    channel = models.CharField(max_length=10, choices=CHANNELS, default=OFFICE)
    reference = models.CharField(max_length=80, blank=True, help_text="Bank or mobile-money reference")
    note = models.CharField(max_length=200, blank=True)
    receipt_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    # Mobile money through Paynow
    phone = models.CharField(max_length=20, blank=True)
    wa_id = models.CharField(max_length=32, blank=True, help_text="WhatsApp number to send the receipt to")
    paynow_reference = models.CharField(max_length=40, blank=True)
    poll_url = models.URLField(max_length=300, blank=True)
    paynow_status = models.CharField(max_length=40, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def reference_for_paynow(self):
        return f"SE-{self.pk}"

    def mark_paid(self, when=None):
        """Idempotent. Returns True only the first time."""
        if self.status == self.PAID:
            return False
        self.status = self.PAID
        self.paid_at = when or timezone.now()
        self.receipt_number = f"R{timezone.localtime(self.paid_at):%y%m}-{self.pk:05d}"
        self.save(update_fields=["status", "paid_at", "receipt_number", "paynow_reference", "paynow_status"])
        return True

    def __str__(self):
        return f"{self.receipt_number or self.pk} {self.currency} {self.amount} ({self.status})"
