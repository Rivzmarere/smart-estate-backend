
from django.urls import  path

from parameters.views.views_complaint_category import ComplaintCategorysList,ComplaintCategorysDetails,ComplaintCategorysPaginated


urlpatterns = [
  
    path("complaint-category",  ComplaintCategorysList.as_view()),
    path("complaint-category-paginated",  ComplaintCategorysPaginated.as_view()),
    path("complaint-category/<int:id>",  ComplaintCategorysDetails.as_view()),

]