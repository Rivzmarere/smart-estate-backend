from django.urls import path

from .views import GateDailyReport

urlpatterns = [
    path("reports/gate-daily", GateDailyReport.as_view()),
]
