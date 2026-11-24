"""
Walk-in approval: a visitor arrives without a code, the guard asks the
resident on WhatsApp, and the resident taps Approve or Decline.
"""

from estates.models import EstateScoped

from datetime import timedelta

from django.db import models
from django.utils import timezone

from authentication.models import User
from home.models import Home
from parameters.models.models_transport_type import TransportType
from visit.models import Visit

# After this the guard must ask again (or phone the resident).
REQUEST_LIFETIME = timedelta(minutes=10)


class WalkInRequest(EstateScoped):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"
    STATUSES = [(PENDING, "Waiting for resident"), (APPROVED, "Approved"), (DECLINED, "Declined"), (EXPIRED, "No answer")]

    WHATSAPP = "whatsapp"
    PHONE_CALL = "phone"
    ANSWER_CHANNELS = [(WHATSAPP, "WhatsApp"), (PHONE_CALL, "Phone call to the guard")]

    home = models.ForeignKey(Home, on_delete=models.PROTECT, related_name="walk_ins")
    stand_number = models.IntegerField()
    address = models.CharField(max_length=200)
    resident_phone = models.CharField(max_length=20, blank=True)
    visitor_name = models.CharField(max_length=60)
    visitor_national_id = models.CharField(max_length=20, blank=True)
    vehicle = models.CharField(max_length=20, blank=True)
    transport_type = models.ForeignKey(TransportType, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    whatsapp_sent = models.BooleanField(default=False)
    answered_via = models.CharField(max_length=10, choices=ANSWER_CHANNELS, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="walk_ins_requested")
    visit = models.OneToOneField(Visit, on_delete=models.SET_NULL, null=True, blank=True, related_name="walk_in")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def expires_at(self):
        return self.created_at + REQUEST_LIFETIME

    def expire_if_stale(self):
        if self.status == self.PENDING and timezone.now() > self.expires_at:
            self.status = self.EXPIRED
            self.save(update_fields=["status"])
        return self.status

    def __str__(self):
        return f"{self.visitor_name} -> stand {self.stand_number} ({self.status})"
