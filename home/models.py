from django.db import models

from authentication.models import User
from owner.models import Owner
from parameters.models.models_home_status import HomeStatus
from resident.models import Resident
from stand.models import Stand

# Create your models here.

class Home(models.Model):
   owner = models.ForeignKey(Owner, on_delete=models.CASCADE)
   stand = models.ForeignKey(Stand, on_delete=models.CASCADE)
   resident = models.ForeignKey(Resident, on_delete=models.CASCADE,null=True,blank=True)
   home_status = models.ForeignKey(HomeStatus, on_delete=models.CASCADE)
   authorized_by = models.ForeignKey(User, on_delete=models.CASCADE)
   date_created = models.DateTimeField(auto_now_add=True)
   status = models.BooleanField(default=False)

