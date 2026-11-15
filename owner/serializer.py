from smartEstateBackend.audit import StampAuthorizedBy
from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Owner

class OwnerReadSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Owner
        fields = '__all__'
        depth = 1

class OwnerWriteSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = '__all__'
        
class OwnerUpdateSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = ['status']
