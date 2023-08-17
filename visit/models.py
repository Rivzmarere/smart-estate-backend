from django.db import models

from authentication.models import User
from home.models import Home
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus

# Create your models here.

class Visit(models.Model):
    stand_number = models.IntegerField()
    home = models.CharField(max_length=200)
    visit_code = models.CharField(max_length=60)
    resident_phone_number = models.CharField(max_length=20, null=True,blank=True)
    visitor_name = models.CharField(max_length=60)
    visitor_vehicle_reg_number = models.CharField(max_length=20, null=True,blank=True)
    visitor_national_id = models.CharField(max_length=25)
    transport_type = models.ForeignKey(TransportType, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_arrived = models.DateTimeField(null=True,blank=True)
    date_depature = models.DateTimeField(auto_now=True)
    visit_status = models.ForeignKey(VisitStatus, on_delete=models.CASCADE)
    authorized_by = models.ForeignKey(User, on_delete=models.CASCADE,null=True,blank=True)
    status = models.BooleanField(default=True)
