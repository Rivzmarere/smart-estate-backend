from smartEstateBackend.audit import StampAuthorizedBy
from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Stand

class StandReadSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Stand
        fields = '__all__'
        depth = 1

class StandWriteSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Stand
        fields = '__all__'
        