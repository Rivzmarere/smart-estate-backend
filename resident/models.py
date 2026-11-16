from estates.models import EstateScoped
from django.db import models

from authentication.models import User
from parameters.models.models_gender import Gender
from parameters.models.models_nationality import Nationality
from parameters.models.models_visit_status import VisitStatus


# Create your models here.

class Resident(EstateScoped):
    name = models.CharField(max_length=60)
    surname = models.CharField(max_length=60)
    id_number = models.CharField(max_length=20)
    # Optional: tenants added by their landlord from the portal may not give these.
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE, null=True, blank=True)
    nationality = models.ForeignKey(Nationality, on_delete=models.CASCADE, null=True, blank=True)
    phone_number1 = models.CharField(max_length=20, null=True,blank=True)
    phone_number2 = models.CharField(max_length=20, null=True,blank=True)
    phone_number3 = models.CharField(max_length=20, null=True,blank=True)
    phone_number4 = models.CharField(max_length=20, null=True,blank=True)
    email = models.CharField(max_length=60, null=True,blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_edited = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=True)
    authorized_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

