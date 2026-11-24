from django.urls import path

from .views import ManageNotice, ManageNotices, PublicNotices

urlpatterns = [
    path("notices", PublicNotices.as_view()),
    path("notices/manage", ManageNotices.as_view()),
    path("notices/manage/<int:id>", ManageNotice.as_view()),
]
