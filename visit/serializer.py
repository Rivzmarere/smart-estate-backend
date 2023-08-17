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
        fields = ['stand_number','resident_phone_number','visitor_name','transport_type','visit_status']
        

class VisitBookinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = ['visitor_national_id','authorized_by','visit_status','date_arrived']
        
class VisitBookOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = ['visit_status',]
        
