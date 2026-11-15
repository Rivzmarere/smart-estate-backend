from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Owner

class OwnerReadSerializer(serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Owner
        fields = '__all__'
        depth = 1

class OwnerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = '__all__'
        
class OwnerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = ['status']
