from django.db import models

from authentication.models import User
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus

from stand.models import Stand

# Create your models here.

class Complain(models.Model):
    stand_number = models.ForeignKey(Stand, on_delete=models.CASCADE)
    complain_code = models.CharField(max_length=60)
    resident_phone_number = models.CharField(max_length=20)
    description = models.TextField(max_length=200)
    complaint_category = models.ForeignKey(ComplaintCategory, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now_add=True)
    compalint_status = models.ForeignKey(ComplaintStatus, on_delete=models.CASCADE)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.BooleanField(default=False)


