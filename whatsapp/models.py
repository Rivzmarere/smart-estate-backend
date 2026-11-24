from django.db import models


class WhatsAppSession(models.Model):
    """Where one WhatsApp number is in a conversation with the bot."""

    wa_id = models.CharField(max_length=32, unique=True, help_text="WhatsApp number in international format, e.g. 263772111111")
    state = models.CharField(max_length=40, default="menu")
    data = models.JSONField(default=dict, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.wa_id} ({self.state})"


class MessageLog(models.Model):
    """Audit trail of every message in and out (also used to ignore duplicate deliveries)."""

    INBOUND = "in"
    OUTBOUND = "out"
    DIRECTIONS = [(INBOUND, "Inbound"), (OUTBOUND, "Outbound")]

    wa_id = models.CharField(max_length=32, db_index=True)
    direction = models.CharField(max_length=3, choices=DIRECTIONS)
    message_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    payload = models.JSONField(default=dict)
    ok = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
