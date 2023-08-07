from dataclasses import fields
from rest_framework import serializers
from .models import Provider

class ProviderReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = '__all__'
        depth = 1

class ProviderWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        exclude = ['stand_number','resident_phone_number','service_description','provider_category']
        