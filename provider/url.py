
from django.urls import  path
from .views import ProviderList,ProviderDetails,ProviderPaginated

urlpatterns = [
    path("provider",  ProviderList.as_view()),
    path("provider-paginated",  ProviderPaginated.as_view()),
    path("provider/<int:id>",  ProviderDetails.as_view()),
  


]