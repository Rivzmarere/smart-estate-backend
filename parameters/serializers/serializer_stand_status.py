from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_stand_status import StandStatus



class StandStatusReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandStatus
        fields = '__all__'
        depth = 1

class StandStatusWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandStatus
        fields = ['name']
        
