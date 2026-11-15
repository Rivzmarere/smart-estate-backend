"""
Help for residents beyond the bot's menus:
  * EmergencyAlert: raised from WhatsApp, shown on the gate screen, SMSed to
    the estate's emergency numbers;
  * Conversation: the resident chats with the estate office, who answer
    from the back-office inbox.
"""

from django.db import models

from authentication.models import User
from estates.models import EstateScoped
from home.models import Home


class EmergencyAlert(EstateScoped):
    SECURITY = "security"
    MEDICAL = "medical"
    FIRE = "fire"
    OTHER = "other"
    KINDS = [(SECURITY, "Security / intruder"), (MEDICAL, "Medical"), (FIRE, "Fire"), (OTHER, "Other emergency")]

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    STATUSES = [(OPEN, "New"), (ACKNOWLEDGED, "Responding"), (RESOLVED, "Resolved")]

    home = models.ForeignKey(Home, on_delete=models.PROTECT, related_name="emergencies")
    stand_number = models.IntegerField()
    address = models.CharField(max_length=200)
    resident_name = models.CharField(max_length=130, blank=True)
    wa_id = models.CharField(max_length=32)
    kind = models.CharField(max_length=10, choices=KINDS)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=13, choices=STATUSES, default=OPEN)
    sms_sent_to = models.CharField(max_length=200, blank=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Conversation(EstateScoped):
    OPEN = "open"
    CLOSED = "closed"
    STATUSES = [(OPEN, "Open"), (CLOSED, "Closed")]

    home = models.ForeignKey(Home, on_delete=models.PROTECT, related_name="conversations")
    stand_number = models.IntegerField()
    address = models.CharField(max_length=200)
    resident_name = models.CharField(max_length=130, blank=True)
    wa_id = models.CharField(max_length=32, db_index=True)
    status = models.CharField(max_length=6, choices=STATUSES, default=OPEN)
    unread = models.PositiveIntegerField(default=0, help_text="Resident messages the office has not opened yet")
    last_message_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]


class ConversationMessage(EstateScoped):
    FROM_RESIDENT = "in"
    FROM_OFFICE = "out"
    DIRECTIONS = [(FROM_RESIDENT, "Resident"), (FROM_OFFICE, "Office")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTIONS)
    text = models.TextField()
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    delivered = models.BooleanField(default=True, help_text="For office messages: WhatsApp accepted it")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
