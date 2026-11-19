"""
A record of every spreadsheet loaded into an estate: who loaded it, what it
created, and enough to undo it while nothing else depends on those records.
"""

from django.db import models

from authentication.models import User
from estates.models import EstateScoped


class ImportBatch(EstateScoped):
    kind = models.CharField(max_length=20)
    filename = models.CharField(max_length=200)
    rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True, help_text="What was created, e.g. {'homes': 120, 'owners': 98}")
    created_ids = models.JSONField(default=dict, blank=True, help_text="{'app_label.model': [ids]} for undo")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.kind} from {self.filename} ({self.rows} rows)"
