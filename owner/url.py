
from django.urls import  path
from .views import OwnerList,OwnerDetails,OwnerPaginated

urlpatterns = [
    path("owner",  OwnerList.as_view()),
    path("owner-paginated",  OwnerPaginated.as_view()),
    path("owner/<int:id>",  OwnerDetails.as_view()),
  


]