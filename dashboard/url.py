from django.urls import path

from .views import EstateDashboard

urlpatterns = [
    path("dashboard", EstateDashboard.as_view()),
]
