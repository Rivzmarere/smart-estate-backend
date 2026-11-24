from smartEstateBackend.audit import StampAuthorizedBy
from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Home

class HomeReadSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Home
        fields = '__all__'
        depth = 1

class HomeWriteSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['owner','stand','home_status','authorized_by','resident','address']
        
class HomeResidentUpdateSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['resident']

class HomeStatusUpdateSerializer(StampAuthorizedBy, serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['home_status','address']