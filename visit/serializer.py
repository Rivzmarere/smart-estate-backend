from rest_framework import serializers

from authentication.serializer import UserSummarySerializer
from sms.sender import zimbabwe_mobile

from .models import Visit

class VisitReadSerializer(serializers.ModelSerializer):
    authorized_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Visit
        fields = '__all__'
        depth = 1

class VisitWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = ['stand_number','resident_phone_number','visitor_name','visitor_phone_number','transport_type','visit_status']

    def validate_visitor_phone_number(self, value):
        if value in (None, ""):
            return None
        number = zimbabwe_mobile(value)
        if not number:
            raise serializers.ValidationError("Enter a Zimbabwean mobile number, e.g. 0772 123 456.")
        return number
        

class VisitBookinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = ['visitor_national_id','authorized_by','visit_status','date_arrived']
        
class VisitBookOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = ['visit_status',]
        
