from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from .models import WhiteList, WhiteListGuest

class WhiteListGuestReadSerializer(serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = WhiteListGuest
        fields = '__all__'
        depth = 1

class WhiteListGuestWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhiteListGuest
        fields = ['stand_number','resident_phone_number','visitor_name','visitor_national_id','authorized_by']
        


class WhiteListReadSerializer(serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = WhiteList
        fields = '__all__'
        depth = 1

class WhiteListBookInSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhiteList
        fields = ['white_list_guest','transport_type','authorized_by','visit_status']
        

class WhiteListBookOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhiteList
        fields = ['visit_status']
        
