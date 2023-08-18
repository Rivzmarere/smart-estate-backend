
from django.urls import  path
from .views import WhiteListGuestList,WhiteListGuestPaginated,WhiteListGuestDetails,WhiteListPaginated,WhiteListBookInDetails,WhiteListBookOutDetails

urlpatterns = [
    path("white-list-guest",  WhiteListGuestList.as_view()),
    path("white-list-guest-paginated",  WhiteListGuestPaginated.as_view()),
    path("white-list-guest/<int:id>",  WhiteListGuestDetails.as_view()),
    path("white-list-paginated",  WhiteListPaginated.as_view()),
    path("white-list-book-in",  WhiteListBookInDetails.as_view()),
    path("white-list-book-out/<int:id>",  WhiteListBookOutDetails.as_view()),
]