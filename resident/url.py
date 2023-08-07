
from django.urls import  path
from .views import ResidentList,ResidentDetails,ResidentPaginated

urlpatterns = [
  

    path("resident",  ResidentList.as_view()),
    path("resident-paginated",  ResidentPaginated.as_view()),
    path("resident/<int:id>",  ResidentDetails.as_view()),
  

]