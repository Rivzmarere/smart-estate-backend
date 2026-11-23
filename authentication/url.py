from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from authentication.views import MyTokenObtainPairView

from .views import MyAccount, MyPassword, ResetUserPassword, SignUpView, UserDetails, AllUserList, AllUserPaginated

urlpatterns = [
    path('token',MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('users-all', AllUserList.as_view()),
    path('users-paginated', AllUserPaginated.as_view()),
    path("users-signUp",SignUpView.as_view(), name='signUp'),
    path("users-details/<int:id>",UserDetails.as_view(), name='user-details'),
    path("users-details/<int:id>/reset-password", ResetUserPassword.as_view()),
    path("account", MyAccount.as_view()),
    path("account/password", MyPassword.as_view()),

]