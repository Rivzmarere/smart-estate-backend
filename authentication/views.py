import math
from rest_framework import  status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from .models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import IsAuthenticated
from .serializer import ChangePasswordSerializer, SignUpSerializer,ReadUserSerializer,UpdateUserSerializer

class SignUpView(GenericAPIView):
    serializer_class = SignUpSerializer
    permission_classes = []
    def post(self, request: Request):
        data = request.data
        username = data.get("username")
        email = data.get("email")
        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            serializer.save()
            print(data)
            current_site = get_current_site(request).domain
            relativeLink = reverse('signUp')
            absurl = 'http://'+current_site+relativeLink
            email_body = 'Hi '+ username + \
                ' Use the link below to verify your email \n' + absurl
            data = {'email_body': email_body, 'to_email': email,
                    'email_subject': 'Verify your email'}
            # Util.send_email(data)
            response = {"message": "User Created Successfully Check Email For verification Link", "data": serializer.data}
            return Response(data=response, status=status.HTTP_201_CREATED)

        return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GetAgents(GenericAPIView):
    serializer_class = ReadUserSerializer
    def get(self, request, format=None):
        sales = User.objects.all()
        sales = sales.filter(role ='Driver')
        serializer = ReadUserSerializer(sales, many=True)
        return Response({'data':serializer.data},status=status.HTTP_200_OK)


class AllUserList(GenericAPIView):
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

class AllDriverList(GenericAPIView):
    serializer_class = ReadUserSerializer 
    def get(self, request, format=None):
        sort = request.GET.get('sort')
        page = int(request.GET.get('page',1))
        per_page = 9
        users = User.objects.all()
        if sort =='asc':
            users = users.order_by('date_joined').filter(role='Driver')
        
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


class ChangePasswordView(GenericAPIView):
        """
        An endpoint for changing password.
        """
        serializer_class = ChangePasswordSerializer
        model = User
        permission_classes = (IsAuthenticated,)

        def get_object(self, id):
            try:
                return User.objects.get(pk=id)
            except User.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)

        def put(self, request,id, *args, **kwargs):
            self.object = self.get_object(id)
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                # Check old password
                if not self.object.check_password(serializer.data.get("old_password")):
                    return Response({"old_password": "Wrong password. Old Password"}, status=status.HTTP_400_BAD_REQUEST)
                # set_password also hashes the password that the user will get
                self.object.set_password(serializer.data.get("new_password"))
                self.object.save()
                response = {
                    'status': 'success',
                    'code': status.HTTP_200_OK,
                    'message': 'Password updated successfully',
                }
                return Response(data=response, status=status.HTTP_200_OK)


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

