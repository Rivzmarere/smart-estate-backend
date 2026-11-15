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
from .serializer import ChangePasswordSerializer, SignUpSerializer,ReadUserSerializer,UpdateUserSerializer

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
        sort = request.GET.get('sort')
        page = int(request.GET.get('page',1))
        per_page = 9
        users = estate_users()
        if sort =='asc':
            users = users.order_by('date_joined')
        
        total = users.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ReadUserSerializer(users[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })

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
        estate = user.estate or (None if user.is_superuser else Estate.objects.filter(active=True).first())
        token['estate'] = estate.name if estate else "All estates"
        token['estate_slug'] = estate.slug if estate else ""
        token['platform'] = bool(user.is_superuser and not user.estate_id)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if self.user.estate_id and not self.user.estate.active:
            raise AuthenticationFailed("This estate's account is switched off. Please contact Smart Estate.")
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


class ChangePasswordView(GenericAPIView):
        """
        An endpoint for changing password.
        """
        serializer_class = ChangePasswordSerializer
        model = User
        permission_classes = (IsAuthenticated,)

        def get_object(self, id):
            if int(id) == self.request.user.pk:
                return self.request.user
            return get_object_or_404(estate_users(), pk=id)

        def put(self, request, id, *args, **kwargs):
            self.object = self.get_object(id)
            # Users may change only their own password; admins may change anyone's.
            if self.object.pk != request.user.pk and not is_admin(request.user):
                return Response({"errors": "You can only change your own password."}, status=status.HTTP_403_FORBIDDEN)
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": "Wrong password. Old Password"}, status=status.HTTP_400_BAD_REQUEST)
            new_password = serializer.data.get("new_password")
            try:
                validate_password(new_password, user=self.object)
            except DjangoValidationError as exc:
                return Response({"new_password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
            self.object.set_password(new_password)
            self.object.save()
            return Response(
                {"status": "success", "code": status.HTTP_200_OK, "message": "Password updated successfully"},
                status=status.HTTP_200_OK,
            )


# class ResetPassword(GenericAPIView):
#     @receiver(reset_password_token_created)
#     def password_reset_token_created(sender, instance, reset_password_token, *args, **kwargs):
#         # send an e-mail to the user
#         current_site = '127.0.0.1:8000'
#         relativeLink = reverse('signUp')
#         reset_password_url = "{}?token={}".format(
#             instance.request.build_absolute_uri(reverse('password_reset:reset-password-confirm')),
#             reset_password_token.key)
    
#         absurl = 'http://'+current_site+relativeLink
#         email_body = 'Hi '+ reset_password_token.user.username +' '+ \
#             ' Use the link below to verify your email \n' + reset_password_url
#         data = {'email_body': email_body, 'to_email': reset_password_token.user.email,
#                 'email_subject': 'Verify your email'}
#         context = {
#             'current_user': reset_password_token.user,
#             'username': reset_password_token.user.username,
#             'email': reset_password_token.user.email,
#         }
#         print(data)

#         # # render email text
#         # email_plaintext_message = render_to_string('email/user_reset_password.txt', context)

#         # msg = EmailMultiAlternatives(
#         #     # title:
#         #     "Password Reset for {title}".format(title="Some website title"),
#         #     # message:
#         #     email_plaintext_message,
#         #     # from:
#         #     "rivaldoTest@outlook.com",
#         #     # to:
#         #     [reset_password_token.user.email]
#         # )
#         # msg.attach_alternative(email_html_message, "text/html")
#         # msg.send()
#         return Response(data=data, status=status.HTTP_200_OK)

class UpdatedUser(GenericAPIView):
    def validate_email(self, value,id):
        user = self.context['request'].user
        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise UpdateUserSerializer.ValidationError({"email": "This email is already in use."})
        return value

    def validate_username(self, value):
        user = self.context['request'].user
        if User.objects.exclude(pk=user.pk).filter(username=value).exists():
            raise UpdateUserSerializer.ValidationError({"username": "This username is already in use."})
        return value

    def update(self, instance, validated_data):
        instance.first_name = validated_data['first_name']
        instance.last_name = validated_data['last_name']
        instance.email = validated_data['email']
        instance.username = validated_data['username']

        instance.save()

