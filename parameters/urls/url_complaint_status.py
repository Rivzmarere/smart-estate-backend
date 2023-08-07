
from django.urls import  path
from parameters.views.views_complaint_status import ComplaintStatusPaginated,ComplaintStatusDetails,ComplaintStatusList

urlpatterns = [
     path("complaint-status",  ComplaintStatusList.as_view()),
    path("complaint-status-paginated",  ComplaintStatusPaginated.as_view()),
    path("complaint-status/<int:id>",  ComplaintStatusDetails.as_view()),


]