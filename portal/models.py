"""
The residents' portal (and USSD): who belongs to a home, changes to the
household, and one-time login codes.

A phone number can be linked to a home in three ways:
  * owner     the Owner of the home (may be a landlord living elsewhere)
  * resident  the home's main resident: the tenant, or the owner living there
  * member    a HouseholdMember: family, a domestic worker, a co-tenant
"""

from django.db import models
from django.utils import timezone

from estates.models import Estate, EstateScoped
from home.models import Home


class HouseholdMember(EstateScoped):
    FAMILY = "family"
    TENANT = "tenant"
    WORKER = "worker"
    OTHER = "other"
    RELATIONSHIPS = [(FAMILY, "Family"), (TENANT, "Co-tenant"), (WORKER, "Domestic worker"), (OTHER, "Other")]

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="members")
    name = models.CharField(max_length=60)
    surname = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=20, help_text="+2637XXXXXXXX")
    relationship = models.CharField(max_length=10, choices=RELATIONSHIPS, default=FAMILY)
    can_book_visitors = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    @property
    def full_name(self):
        return f"{self.name} {self.surname}".strip()


class HouseholdRequest(EstateScoped):
    """A change to a household asked for in the portal; applied at once or after the office approves."""

    ADD_MEMBER = "add_member"
    REMOVE_MEMBER = "remove_member"
    NEW_RESIDENT = "new_resident"
    RESIDENT_LEAVES = "resident_leaves"
    KINDS = [
        (ADD_MEMBER, "Add a household member"),
        (REMOVE_MEMBER, "Remove a household member"),
        (NEW_RESIDENT, "New main resident (tenant moving in)"),
        (RESIDENT_LEAVES, "Main resident moving out"),
    ]

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STATUSES = [(PENDING, "Waiting for the office"), (APPROVED, "Done"), (REJECTED, "Not approved"), (CANCELLED, "Cancelled")]

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="household_requests")
    kind = models.CharField(max_length=20, choices=KINDS)
    details = models.JSONField(default=dict)
    requested_by_phone = models.CharField(max_length=20)
    requested_by_role = models.CharField(max_length=10)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    office_note = models.CharField(max_length=300, blank=True)
    decided_by = models.ForeignKey("authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class LoginCode(models.Model):
    """A one-time code sent by SMS to sign in to the portal. Only a hash is stored."""

    estate = models.ForeignKey(Estate, on_delete=models.CASCADE, related_name="+")
    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    @property
    def usable(self):
        return not self.used and self.attempts < 5 and timezone.now() < self.expires_at
