
from django.urls import  path
from parameters.views.views_provider_category import ProviderCategoryDetails,ProviderCategoryList,ProviderCategoryPaginated

urlpatterns = [
    path("provider-category",  ProviderCategoryList.as_view()),
    path("provider-category-paginated",  ProviderCategoryPaginated.as_view()),
    path("provider-category/<int:id>",  ProviderCategoryDetails.as_view()),


]