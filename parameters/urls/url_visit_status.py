
from django.urls import  path
from parameters.views.views_visit_status import VisitStatusPaginated,VisitStatusDetails,VisitStatusList

urlpatterns = [
    path("visit-status",  VisitStatusList.as_view()),
    path("visit-status-paginated",  VisitStatusPaginated.as_view()),
    path("visit-status/<int:id>",  VisitStatusDetails.as_view()),


]