from dataclasses import fields
from rest_framework import serializers
from .models import Home

class HomeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = '__all__'
        depth = 1

class HomeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['owner','stand','home_status','authorized_by','resident']
        
class HomeResidentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['resident']

class HomeStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['home_status']