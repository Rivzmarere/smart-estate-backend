
from django.urls import  path
from parameters.views.views_user_type import UserTypeDetails,UserTypeList,UserTypePaginated

urlpatterns = [
    path("user-type",  UserTypeList.as_view()),
    path("user-type-paginated",  UserTypePaginated.as_view()),
    path("user-type/<int:id>",  UserTypeDetails.as_view()),
]