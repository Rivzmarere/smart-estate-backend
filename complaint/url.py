
from django.urls import  path
from .views import ComplainList,ComplainPaginated,ComplainDetails

urlpatterns = [
    path("complain",  ComplainList.as_view()),
    path("complain-paginated",  ComplainPaginated.as_view()),
    path("complain/<int:id>",  ComplainDetails.as_view()),
]