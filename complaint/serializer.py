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
        fields = ["stand_number","resident_phone_number", "description","complaint_category","compalint_status"]
        

class ComplainAssignUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complain
        fields = ["assigned_to","compalint_status"]


class ComplainUpdateStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complain
        fields = ["compalint_status"]
        