from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from authentication.views import MyTokenObtainPairView

from .views import SignUpView,UserDetails,AllUserList

urlpatterns = [
    path('token',MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('users-all', AllUserList.as_view()),
    path('users-paginated', AllUserList.as_view()),
    path("users-signUp",SignUpView.as_view(), name='signUp'),
    path("users-details/<int:id>",UserDetails.as_view(), name='signUp'),

]