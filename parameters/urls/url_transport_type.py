
from django.urls import  path
from parameters.views.views_transport_type import TransportTypePaginated,TransportTypeDetails,TransportTypeList

urlpatterns = [
    path("transport-type",  TransportTypeList.as_view()),
    path("transport-type-paginated",  TransportTypePaginated.as_view()),
    path("transport-type/<int:id>",  TransportTypeDetails.as_view()),


]