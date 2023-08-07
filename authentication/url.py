from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from authentication.views import MyTokenObtainPairView

from .views import SignUpView,GetAgents

urlpatterns = [
    path('token',MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('drivers-list', GetAgents.as_view()),
    path("auth/signUp",SignUpView.as_view(), name='signUp'),

]