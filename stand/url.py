
from django.urls import  path
from .views import StandList,StandDetails,StandPaginated

urlpatterns = [
    path("stand",  StandList.as_view()),
    path("stand-paginated",  StandPaginated.as_view()),
    path("stand/<int:id>",  StandDetails.as_view()),
  

]