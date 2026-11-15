from django.urls import path

from .views import webhook

urlpatterns = [
    path("whatsapp/webhook", webhook, name="whatsapp-webhook"),
]
