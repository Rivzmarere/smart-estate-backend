from rest_framework import serializers
from rest_framework.validators import ValidationError
from django.contrib.auth.password_validation import validate_password

from smartEstateBackend.permissions import ROLES
from .models import User


class SignUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "password","role","first_name","last_name"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate_role(self, value):
        if value not in ROLES:
            raise ValidationError(f"Role must be one of: {', '.join(ROLES)}")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):

        username_exists = User.objects.filter(username=attrs["username"]).exists()

        if username_exists:
            raise ValidationError("Username has already been used")

        return super().validate(attrs)

    def create(self, validated_data):
        password = validated_data.pop("password")

        user = super().create(validated_data)

        user.set_password(password)

        user.save()


        return user


class ReadUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id","role", "username",'is_active','first_name','last_name','date_joined']



class UserSummarySerializer(serializers.ModelSerializer):
    """Safe nested representation of a user (never exposes the password hash)."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "role"]
