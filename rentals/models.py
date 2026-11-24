"""
Renting out properties: leases, rent and what each property costs.

A property is a Home (with its Stand as the reference number). A Lease puts
a tenant in it for a monthly rent. Rent is billed as levy.Invoice rows of
kind "rent" and paid through the same payments as levies (EcoCash, cash,
bank), so receipts, the WhatsApp bot, USSD and the portal all work for rent.

Each invoice and payment carries its lease, so a tenant's account is their
own: the next tenant of the same property starts from zero.

The deposit is held outside the rent account: what was asked, what was
received, and at the end what went back to the tenant or was kept.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from authentication.models import User
from estates.models import EstateScoped
from home.models import Home
from resident.models import Resident


def lease_document_path(lease, filename):
    return f"leases/{lease.estate_id}/{lease.pk}/{filename}"


class Lease(EstateScoped):
    ACTIVE = "active"
    ENDED = "ended"
    STATUSES = [(ACTIVE, "Active"), (ENDED, "Ended")]

    home = models.ForeignKey(Home, on_delete=models.PROTECT, related_name="leases")
    tenant = models.ForeignKey(Resident, on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Empty = month to month")
    rent_usd = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    due_day = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(28)], help_text="Day of the month rent is due")
    deposit_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    deposit_paid_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE)
    notes = models.TextField(blank=True)
    # Moving out
    ended_on = models.DateField(null=True, blank=True)
    end_reason = models.CharField(max_length=200, blank=True)
    deposit_returned_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_deducted_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Kept for unpaid rent or damage")
    # The signed agreement (served only to staff)
    document = models.FileField(upload_to=lease_document_path, blank=True)
    document_name = models.CharField(max_length=120, blank=True)
    document_type = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["home"], condition=models.Q(status="active"), name="one_active_lease_per_property"),
        ]

    @property
    def deposit_held_usd(self):
        return self.deposit_paid_usd - self.deposit_returned_usd - self.deposit_deducted_usd

    def __str__(self):
        return f"{self.home.address}: {self.tenant.name} {self.tenant.surname} from {self.start_date}"


class Expense(EstateScoped):
    REPAIRS = "repairs"
    RATES = "rates"
    UTILITIES = "utilities"
    INSURANCE = "insurance"
    OTHER = "other"
    CATEGORIES = [
        (REPAIRS, "Repairs and maintenance"),
        (RATES, "Rates and levies"),
        (UTILITIES, "Water and electricity"),
        (INSURANCE, "Insurance"),
        (OTHER, "Other"),
    ]

    home = models.ForeignKey(Home, on_delete=models.PROTECT, null=True, blank=True, related_name="expenses", help_text="Empty = the whole portfolio")
    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=10, choices=CATEGORIES, default=REPAIRS)
    description = models.CharField(max_length=200)
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    paid_to = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
