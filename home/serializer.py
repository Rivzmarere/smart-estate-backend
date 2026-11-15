from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import Home

class HomeReadSerializer(serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Home
        fields = '__all__'
        depth = 1

class HomeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['owner','stand','home_status','authorized_by','resident','address']
        
class HomeResidentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['resident']

class HomeStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Home
        fields = ['home_status','address']