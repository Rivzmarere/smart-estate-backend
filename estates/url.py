from django.urls import path

from .views import EstateDetail, EstateFirstAdmin, Estates, MyEstate, PublicEstate

urlpatterns = [
    path("estates", Estates.as_view()),
    path("estates/<int:id>", EstateDetail.as_view()),
    path("estates/<int:id>/admin", EstateFirstAdmin.as_view()),
    path("estate", MyEstate.as_view()),
    path("estate/public", PublicEstate.as_view()),
]
