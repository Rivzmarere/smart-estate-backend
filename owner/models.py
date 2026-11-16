from estates.models import EstateScoped
from django.db import models

from authentication.models import User
from parameters.models.models_gender import Gender
from parameters.models.models_nationality import Nationality

from stand.models import Stand

# Create your models here.

class Owner(EstateScoped):
    name = models.CharField(max_length=60)
    surname = models.CharField(max_length=60)
    id_number = models.CharField(max_length=20)
    # Optional: a landlord adding their own properties need not give these.
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE, null=True, blank=True)
    nationality = models.ForeignKey(Nationality, on_delete=models.CASCADE, null=True, blank=True)
    phone_number1 = models.CharField(max_length=20)
    phone_number2 = models.CharField(max_length=20, blank=True)
    email = models.CharField(max_length=60, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_edited = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=True)
    authorized_by = models.ForeignKey(User, on_delete=models.PROTECT)

