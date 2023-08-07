from dataclasses import fields
from rest_framework import serializers

from parameters.models.models_complaint_category import ComplaintCategory


class ComplaintCategoryReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintCategory
        fields = '__all__'
        depth = 1

class ComplaintCategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintCategory
        fields = ['name']
        
