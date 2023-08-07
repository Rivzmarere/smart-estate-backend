
from django.urls import  path
from parameters.views.views_stand_status import StandStatusPaginated,StandStatusDetails,StandStatusList

urlpatterns = [
    path("stand-status",  StandStatusList.as_view()),
    path("stand-status-paginated",  StandStatusPaginated.as_view()),
    path("stand-status/<int:id>",  StandStatusDetails.as_view()),


]