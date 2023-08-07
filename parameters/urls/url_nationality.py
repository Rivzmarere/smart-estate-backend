
from django.urls import  path
from parameters.views.views_nationality import  NationalityPaginated,NationalityDetails,NationalityList

urlpatterns = [
  
    path("nationality",  NationalityList.as_view()),
    path("nationality-paginated",  NationalityPaginated.as_view()),
    path("nationality/<int:id>",  NationalityDetails.as_view()),

]