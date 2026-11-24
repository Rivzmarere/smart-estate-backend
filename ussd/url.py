from django.urls import path

from .views import gateway

urlpatterns = [path("ussd/<str:secret>", gateway)]
