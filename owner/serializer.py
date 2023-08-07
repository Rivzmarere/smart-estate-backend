from dataclasses import fields
from rest_framework import serializers
from .models import Owner

class OwnerReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = '__all__'
        depth = 1

class OwnerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        exclude = '__all__'
        
class OwnerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = ['status']
