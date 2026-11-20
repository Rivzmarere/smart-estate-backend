
from django.urls import  path
from .views import HomeList, HomeDetails, HomeOverview, HomePaginated

urlpatterns = [
    path("home",  HomeList.as_view()),
    path("home-paginated",  HomePaginated.as_view()),
    path("home/<int:id>",  HomeDetails.as_view()),
    path("home/<int:id>/overview", HomeOverview.as_view()),


]