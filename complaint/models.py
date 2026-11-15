from django.db import models

from authentication.models import User
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus

from stand.models import Stand

# Create your models here.

class Complain(models.Model):
    stand_number = models.IntegerField()
    home = models.CharField(max_length=200)
    complain_code = models.CharField(max_length=60)
    resident_phone_number = models.CharField(max_length=20)
    description = models.TextField(blank=True, null=True)
    complaint_category = models.ForeignKey(ComplaintCategory, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    compalint_status = models.ForeignKey(ComplaintStatus, on_delete=models.CASCADE)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.BooleanField(default=True)



def photo_path(photo, filename):
    return f"complaints/{photo.complaint_id}/{filename}"


class ComplaintPhoto(models.Model):
    """A photo the resident sent with a repair report (served only to staff)."""

    complaint = models.ForeignKey(Complain, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to=photo_path)
    content_type = models.CharField(max_length=40)
    source_media_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
