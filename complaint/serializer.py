from dataclasses import fields
from rest_framework import serializers
from .models import Complain

class ComplainReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complain
        fields = '__all__'
        depth = 1

class ComplainWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complain
        exclude = ['assigned_to']
        
