"""
Who did what: a permanent history of the changes that matter (money, people,
access, settings). Rows are only ever added, never edited or deleted.
"""

from django.conf import settings
from django.db import models


class AuditEntry(models.Model):
    MONEY = "money"
    PEOPLE = "people"
    ACCESS = "access"
    SETTINGS = "settings"
    DATA = "data"
    AREAS = [(MONEY, "Money"), (PEOPLE, "Homes and people"), (ACCESS, "Users and access"), (SETTINGS, "Settings"), (DATA, "Imports")]

    estate = models.ForeignKey("estates.Estate", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    who = models.CharField(max_length=120, blank=True, help_text="Name at the time, kept if the user is removed")
    area = models.CharField(max_length=10, choices=AREAS)
    action = models.CharField(max_length=40, db_index=True)
    summary = models.CharField(max_length=300)
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["estate", "-at"])]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.who}: {self.summary}"
