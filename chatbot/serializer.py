from dataclasses import fields
from rest_framework import serializers
from .models import Chat

class ChatReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = '__all__'
        depth = 1

class ChatWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = '__all__'
        