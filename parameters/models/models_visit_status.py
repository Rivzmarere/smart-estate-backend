from django.db import models

# Create your models here.

class VisitStatus(models.Model):
    name = models.CharField(max_length=20)
    date_created = models.DateTimeField(auto_now_add=True)
    status = models.BooleanField(default=True)

