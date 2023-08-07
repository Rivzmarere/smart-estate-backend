
from django.urls import  path
from parameters.views.views_provider_status import ProviderStatusPaginated,ProviderStatusList,ProviderStatusDetails

urlpatterns = [
    path("provider-status",  ProviderStatusList.as_view()),
    path("provider-status-paginated",  ProviderStatusPaginated.as_view()),
    path("provider-status/<int:id>",  ProviderStatusDetails.as_view()),
]