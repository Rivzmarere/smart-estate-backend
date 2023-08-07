from django.db import models

from authentication.models import User
from parameters.models.models_provider_category import ProviderCategory
from parameters.models.models_provider_status import ProviderStatus
from stand.models import Stand

# Create your models here.

class Provider(models.Model):
    stand_number = models.ForeignKey(Stand, on_delete=models.CASCADE)
    resident_phone_number = models.CharField(max_length=20)
    service_description = models.CharField(max_length=60)
    provider_category =  models.ForeignKey(ProviderCategory, on_delete=models.CASCADE)
    service_provider_name = models.CharField(max_length=60)
    service_provider_contact  = models.CharField(max_length=60)
    service_national_id  = models.CharField(max_length=60)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now_add=True)
    authorized_by = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.BooleanField(default=False)
    service_request_status = models.ForeignKey(ProviderStatus, on_delete=models.CASCADE)
