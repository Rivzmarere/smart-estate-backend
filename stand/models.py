from estates.models import EstateScoped
from django.db import models
from authentication.models import User
from parameters.models.models_stand_status import StandStatus

# Create your models here.
class Stand(EstateScoped):
    stand_number = models.IntegerField()
    stand_status = models.ForeignKey(StandStatus,on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_edited = models.DateTimeField(auto_now=True)
    authorized_by = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.BooleanField(default=True)
