from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_provider_status import ProviderStatus


class ProviderStatusReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderStatus
        fields = '__all__'
        depth = 1

class ProviderStatusWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderStatus
        fields = ['name']
        
