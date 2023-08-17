
from django.urls import  path
from .views import VisitList,VisitPaginated,VisitDetails,VisitBookInUpdateDetails,VisitBookOutUpdateDetails

urlpatterns = [
    path("visit",  VisitList.as_view()),
    path("visit-paginated",  VisitPaginated.as_view()),
    path("visit/<int:id>",  VisitDetails.as_view()),
    path("visit-book-in/<int:id>",  VisitBookInUpdateDetails.as_view()),
    path("visit-book-out/<int:id>",  VisitBookOutUpdateDetails.as_view()),
]