
from django.urls import  path
from .views import VisitList,VisitPaginated,VisitDetails

urlpatterns = [
    path("visit",  VisitList.as_view()),
    path("visit-paginated",  VisitPaginated.as_view()),
    path("visit/<int:id>",  VisitDetails.as_view()),
]