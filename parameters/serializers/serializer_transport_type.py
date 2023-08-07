from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_transport_type import TransportType



class TransportTypeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportType
        fields = '__all__'
        depth = 1

class TransportTypeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportType
        fields = ['name']
        
