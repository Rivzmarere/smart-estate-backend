from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Resident

class ResidentReadSerializer(serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Resident
        fields = '__all__'
        depth = 1

class ResidentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resident
        fields = '__all__'
        
