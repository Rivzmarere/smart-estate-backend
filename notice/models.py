from django.db import models
from django.db.models import Q
from django.utils import timezone

from authentication.models import User


class NoticeQuerySet(models.QuerySet):
    def current(self):
        """Published notices residents should see right now."""
        now = timezone.now()
        return (
            self.filter(published=True, publish_at__lte=now)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("-pinned", "-publish_at")
        )


class Notice(models.Model):
    CATEGORIES = [
        ("general", "General"),
        ("water", "Water"),
        ("power", "Power"),
        ("security", "Security"),
        ("meeting", "Meeting"),
        ("levy", "Levies"),
    ]

    title = models.CharField(max_length=150)
    body = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORIES, default="general")
    pinned = models.BooleanField(default=False, help_text="Shown first")
    published = models.BooleanField(default=True)
    publish_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Hidden after this time")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="notices")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = NoticeQuerySet.as_manager()

    class Meta:
        ordering = ["-pinned", "-publish_at"]

    def __str__(self):
        return self.title
