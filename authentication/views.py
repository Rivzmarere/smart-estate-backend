from smartEstateBackend.listing import flag, number, page, param, search
import math
from rest_framework import  status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from .models import User
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from .serializer import SignUpSerializer, ReadUserSerializer

from django.shortcuts import get_object_or_404
from datetime import timedelta

from estates.context import ALL, current_estate
from estates.models import Estate
from smartEstateBackend.permissions import ROLE_GUARD, IsAdminRole, is_admin


def estate_users():
    """Staff accounts of the current estate (every account for platform staff)."""
    estate = current_estate()
    if estate is ALL:
        return User.objects.all()
    if estate is None:
        return User.objects.none()
    return User.objects.filter(estate=estate)

GUARD_SESSION = timedelta(hours=12)
class SignUpView(GenericAPIView):
    """Create a staff account. Only administrators can create users."""
    permission_classes = [IsAdminRole]
    serializer_class = SignUpSerializer

    def post(self, request: Request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            estate = current_estate()
            if estate is ALL:  # platform staff say which estate the account is for
                estate = Estate.objects.filter(pk=request.data.get("estate")).first()
                if estate is None:
                    return Response({"estate": "Choose the estate this account belongs to."}, status=status.HTTP_400_BAD_REQUEST)
            if estate is None:
                return Response({"estate": "No estate selected."}, status=status.HTTP_400_BAD_REQUEST)
            serializer.save(estate=estate)
            response = {"message": "User created successfully", "data": serializer.data}
            return Response(data=response, status=status.HTTP_201_CREATED)
        return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AllUserList(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ReadUserSerializer 
    def get(self, request, format=None):
        users = estate_users()
        serializer = ReadUserSerializer(users, many=True)
        return Response(
            serializer.data, status=status.HTTP_200_OK)

class AllUserPaginated(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ReadUserSerializer 
    def get(self, request, format=None):
        users = estate_users().order_by("first_name", "last_name", "username")
        if param(request, "search"):
            users = search(users, param(request, "search"), ["username", "first_name", "last_name", "role"])
        active = flag(param(request, "status"))
        if active is not None:
            users = users.filter(is_active=active)
        return page(request, users, ReadUserSerializer)



class UserDetails(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ReadUserSerializer
    def getObject(self, id):
        return get_object_or_404(estate_users(), pk=id)
        
    def get(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ReadUserSerializer(complain)
            return Response(serializer.data, status=status.HTTP_200_OK)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['email'] = user.email
        token['username'] = user.username
        token['name'] = user.get_full_name() or user.username
        organisation = user.organisation if user.spans_organisation else None
        if user.estate_id:
            estate = user.estate
        elif user.is_superuser or organisation:
            estate = None  # they choose an estate in the back office
        else:
            estate = Estate.objects.filter(active=True).first()
        token['estate'] = estate.name if estate else (organisation.name if organisation else "All estates")
        token['estate_slug'] = estate.slug if estate else ""
        token['estate_kind'] = estate.kind if estate else ""
        token['platform'] = bool(user.is_superuser and not user.estate_id)
        token['organisation'] = organisation.name if organisation else ""
        token['organisation_kind'] = organisation.kind if organisation else ""
        token['sandbox'] = bool(estate and estate.sandbox)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if self.user.estate_id and not self.user.estate.active:
            raise AuthenticationFailed("This estate's account is switched off. Please contact Smart Estate.")
        if self.user.organisation_id and not self.user.organisation.active:
            raise AuthenticationFailed("This account is switched off. Please contact Smart Estate.")
        # Guards stay logged in for a whole 12-hour shift so the gate tablet keeps syncing.
        if self.user.role == ROLE_GUARD:
            refresh = self.get_token(self.user)
            access = refresh.access_token
            access.set_exp(lifetime=GUARD_SESSION)
            refresh.set_exp(lifetime=GUARD_SESSION)
            data["refresh"], data["access"] = str(refresh), str(access)
        return data


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


# ---------------------------------------------------------------- my account

def account_row(user):
    role = "Platform" if user.is_superuser and not user.estate_id else user.role
    return {
        "id": user.id, "username": user.username, "first_name": user.first_name, "last_name": user.last_name,
        "email": user.email, "role": role,
        "estate": user.estate.name if user.estate_id else "",
        "organisation": user.organisation.name if user.organisation_id else "",
        "date_joined": user.date_joined, "last_login": user.last_login,
    }


class MyAccount(GenericAPIView):
    """GET my own account; PUT changes my name and email (not my username or role)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(account_row(request.user))

    def put(self, request):
        from django.core.validators import validate_email

        user = request.user
        errors = {}
        first = str(request.data.get("first_name", user.first_name)).strip()[:150]
        last = str(request.data.get("last_name", user.last_name)).strip()[:150]
        email = str(request.data.get("email", user.email) or "").strip().lower()
        if not first:
            errors["first_name"] = "Type your first name."
        if email:
            try:
                validate_email(email)
            except DjangoValidationError:
                errors["email"] = "That is not an email address."
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        user.first_name, user.last_name, user.email = first, last, email
        user.save(update_fields=["first_name", "last_name", "email"])
        return Response(account_row(user))


class MyPassword(GenericAPIView):
    """POST {old_password, new_password}: change my own password."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        user = request.user
        old = request.data.get("old_password") or ""
        new = request.data.get("new_password") or ""
        if not user.check_password(old):
            return Response({"old_password": "That is not your current password."}, status=status.HTTP_400_BAD_REQUEST)
        if not new:
            return Response({"new_password": ["Type a new password."]}, status=status.HTTP_400_BAD_REQUEST)
        if new == old:
            return Response({"new_password": ["The new password must be different."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new, user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new)
        user.save(update_fields=["password"])
        return Response({"detail": "Password changed."})
