
from django.urls import  path
from .views import ComplainUpdateStatusDetails,ComplainList,ComplainPaginated,ComplainDetails,ComplainAssignDetails

urlpatterns = [
    path("complain",  ComplainList.as_view()),
    path("complain-paginated",  ComplainPaginated.as_view()),
    path("complain/<int:id>",  ComplainDetails.as_view()),
    path("complain-assign/<int:id>",  ComplainAssignDetails.as_view()),
    path("complain-update-status/<int:id>",  ComplainUpdateStatusDetails.as_view()),
]