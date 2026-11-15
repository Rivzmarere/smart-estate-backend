import math
from rest_framework import  status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from .models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from .serializer import ChangePasswordSerializer, SignUpSerializer,ReadUserSerializer,UpdateUserSerializer

from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import IsAdminRole, is_admin
class SignUpView(GenericAPIView):
    """Create a staff account. Only administrators can create users."""
    permission_classes = [IsAdminRole]
    serializer_class = SignUpSerializer

    def post(self, request: Request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            response = {"message": "User created successfully", "data": serializer.data}
            return Response(data=response, status=status.HTTP_201_CREATED)
        return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AllUserList(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ReadUserSerializer 
    def get(self, request, format=None):
        users = User.objects.all()
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
        users = User.objects.all()
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
        return get_object_or_404(User, pk=id)
        
    def get(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ReadUserSerializer(complain)
            return Response(serializer.data, status=status.HTTP_200_OK)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['role'] = user.role
        token['email'] = user.email
        # ...

        return token
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
            return get_object_or_404(User, pk=id)

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

