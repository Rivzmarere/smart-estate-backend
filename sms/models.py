from django.db import models


class SmsLog(models.Model):
    """Every SMS the system sends (or tried to send)."""

    to = models.CharField(max_length=20, db_index=True)
    message = models.TextField()
    backend = models.CharField(max_length=20)
    ok = models.BooleanField(default=True)
    provider_id = models.CharField(max_length=128, blank=True, default="")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
