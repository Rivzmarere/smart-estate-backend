from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_complaint_status import ComplaintStatus



class ComplaintStatusReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintStatus
        fields = '__all__'
        depth = 1

class ComplaintStatusWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintStatus
        fields = ['name']
        
