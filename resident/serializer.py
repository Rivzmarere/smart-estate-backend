from dataclasses import fields
from rest_framework import serializers
from .models import Resident

class ResidentReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resident
        fields = '__all__'
        depth = 1

class ResidentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resident
        fields = '__all__'
        
