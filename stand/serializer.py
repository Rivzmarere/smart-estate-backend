from dataclasses import fields
from rest_framework import serializers
from .models import Stand

class StandReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stand
        fields = '__all__'
        depth = 1

class StandWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stand
        fields = '__all__'
        