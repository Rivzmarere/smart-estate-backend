from django.urls import path

from . import office_views as office
from . import views

H = "resident/homes/<int:home_id>"

urlpatterns = [
    path("resident/login/code", views.RequestCode.as_view()),
    path("resident/login/verify", views.VerifyCode.as_view()),
    path("resident/me", views.Me.as_view()),
    path(f"{H}", views.HomeOverview.as_view()),
    path(f"{H}/visitors", views.Visitors.as_view()),
    path(f"{H}/visitors/<int:visit_id>/cancel", views.CancelVisit.as_view()),
    path(f"{H}/walk-ins", views.WalkIns.as_view()),
    path(f"{H}/walk-ins/<int:walk_in_id>/answer", views.AnswerWalkIn.as_view()),
    path(f"{H}/levy", views.Levy.as_view()),
    path(f"{H}/levy/pay", views.Pay.as_view()),
    path(f"{H}/levy/payments/<int:payment_id>", views.PaymentStatus.as_view()),
    path(f"{H}/repairs", views.Repairs.as_view()),
    path(f"{H}/household", views.Household.as_view()),
    path(f"{H}/household/requests", views.HouseholdRequests.as_view()),
    path(f"{H}/household/requests/<int:request_id>/cancel", views.CancelHouseholdRequest.as_view()),
    path(f"{H}/chat", views.Chat.as_view()),
    path(f"{H}/emergency", views.Emergency.as_view()),
    # Estate office
    path("household/requests", office.OfficeRequests.as_view()),
    path("household/requests/<int:id>/decide", office.DecideRequest.as_view()),
    path("household/homes/<int:home_id>", office.HomeHousehold.as_view()),
    path("household/members/<int:member_id>/remove", office.RemoveMember.as_view()),
]
