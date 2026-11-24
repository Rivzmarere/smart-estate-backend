from django.urls import path

from .views import WalkInDecide, WalkInDetail, WalkIns

urlpatterns = [
    path("gate/walk-ins", WalkIns.as_view()),
    path("gate/walk-ins/<int:id>", WalkInDetail.as_view()),
    path("gate/walk-ins/<int:id>/decide", WalkInDecide.as_view()),
]
