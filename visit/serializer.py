from dataclasses import fields
from rest_framework import serializers
from .models import Visit

class VisitReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = '__all__'
        depth = 1

class VisitWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        exclude = ['date_arrived','visitor_national_id','date_depature','visitor_vehicle_reg_number']
        
