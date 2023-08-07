from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_gender import Gender



class GenderReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gender
        fields = '__all__'
        depth = 1

class GenderWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gender
        fields = ['name']
        
