
from django.urls import  path
from .views import ProviderList,ProviderDetails,ProviderPaginated

urlpatterns = [
    path("service-provider",  ProviderList.as_view()),
    path("service-provider-paginated",  ProviderPaginated.as_view()),
    path("service-provider/<int:id>",  ProviderDetails.as_view()),
  


]