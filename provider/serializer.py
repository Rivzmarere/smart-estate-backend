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
        fields = '__all__'
        