from smartEstateBackend.audit import StampAuthorizedBy
from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Provider

class ProviderReadSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Provider
        fields = '__all__'
        depth = 1

class ProviderWriteSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = '__all__'
        

class ProviderPublicSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    """What the resident portal may see: no ID numbers, no staff details."""

    class Meta:
        model = Provider
        fields = ["id", "name", "surname", "address", "phone_number1", "phone_number2", "provider_category", "status"]
        depth = 1
