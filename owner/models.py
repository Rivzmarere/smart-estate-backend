from django.db import models

from authentication.models import User
from parameters.models.models_gender import Gender
from parameters.models.models_nationality import Nationality

from stand.models import Stand

# Create your models here.

class Owner(models.Model):
    stand = models.ForeignKey(Stand, on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    surname = models.CharField(max_length=20)
    id_number = models.CharField(max_length=20)
    date_of_birth = models.DateField()
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE)
    nationality = models.ForeignKey(Nationality, on_delete=models.CASCADE)
    phone_number1 = models.CharField(max_length=20)
    phone_number2 = models.CharField(max_length=20)
    email = models.CharField(max_length=20)
    date_created = models.DateTimeField(auto_now_add=True)
    date_edited = models.DateTimeField(auto_now_add=True)
    status = models.BooleanField(default=False)
    authorized_by = models.ForeignKey(User, on_delete=models.CASCADE)

