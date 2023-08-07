
from django.urls import  path
from parameters.views.views_home_status import HomeStatusPaginated,HomeStatusList,HomeStatusDetails

urlpatterns = [

    path("home-status",  HomeStatusList.as_view()),
    path("home-status-paginated",  HomeStatusPaginated.as_view()),
    path("home-status/<int:id>",  HomeStatusDetails.as_view()),

]