from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_nationality import Nationality



class NationalityReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Nationality
        fields = '__all__'
        depth = 1

class NationalityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Nationality
        fields = ['name']
        
