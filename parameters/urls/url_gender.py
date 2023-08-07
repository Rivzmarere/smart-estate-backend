
from django.urls import  path
from parameters.views.views_gender import GenderDetails,GenderList,GenderPaginated

urlpatterns = [
    path("gender",  GenderList.as_view()),
    path("gender-paginated",  GenderPaginated.as_view()),
    path("gender-category/<int:id>",  GenderDetails.as_view()),


]