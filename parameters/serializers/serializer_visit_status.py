from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_visit_status import VisitStatus


class VisitStatusReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitStatus
        fields = '__all__'
        depth = 1

class VisitStatusWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitStatus
        fields = ['name']
        
