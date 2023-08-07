from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_user_type import UserType



class UserTypeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserType
        fields = '__all__'
        depth = 1

class UserTypeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserType
        fields = ['name']
        
