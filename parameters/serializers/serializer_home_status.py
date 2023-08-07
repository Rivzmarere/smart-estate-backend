from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_home_status import HomeStatus



class HomeStatusReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeStatus
        fields = '__all__'
        depth = 1

class HomeStatusWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeStatus
        fields = ['name']
        
