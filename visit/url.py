from django.urls import path

from .gate import GateBookIn, GateBookOut, GateExpected
from .views import VisitBookInUpdateDetails, VisitBookOutUpdateDetails, VisitDetails, VisitList, VisitPaginated

urlpatterns = [
    path("visit", VisitList.as_view()),
    path("visit-paginated", VisitPaginated.as_view()),
    path("visit/<int:id>", VisitDetails.as_view()),
    path("visit-book-in/<int:id>", VisitBookInUpdateDetails.as_view()),
    path("visit-book-out/<int:id>", VisitBookOutUpdateDetails.as_view()),
    # Guard gate screen (offline-capable tablet)
    path("gate/expected", GateExpected.as_view()),
    path("gate/visits/<int:id>/book-in", GateBookIn.as_view()),
    path("gate/visits/<int:id>/book-out", GateBookOut.as_view()),
]
