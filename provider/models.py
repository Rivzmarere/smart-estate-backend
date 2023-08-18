from django.db import models

from authentication.models import User
from parameters.models.models_provider_category import ProviderCategory
from parameters.models.models_provider_status import ProviderStatus
from stand.models import Stand

# Create your models here.

class Provider(models.Model):
    name = models.CharField(max_length=20)
    surname = models.CharField(max_length=20)
    address = models.CharField(max_length=60)
    id_number = models.CharField(max_length=20)
    phone_number1 = models.CharField(max_length=20)
    phone_number2 = models.CharField(max_length=20, null=True,blank=True)
    provider_category =  models.ForeignKey(ProviderCategory, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    authorized_by = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.BooleanField(default=True)
