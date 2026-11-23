from django.urls import path

from .views import History

urlpatterns = [path("audit", History.as_view())]
