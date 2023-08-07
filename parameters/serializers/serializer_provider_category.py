from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_provider_category import ProviderCategory



class ProviderCategoryReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderCategory
        fields = '__all__'
        depth = 1

class ProviderCategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderCategory
        fields = ['name']
        
