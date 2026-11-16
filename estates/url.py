from django.urls import path

from . import sandbox_views as sb
from .views import EstateDetail, EstateFirstAdmin, Estates, MyEstate, PublicEstate

urlpatterns = [
    path("estates", Estates.as_view()),
    path("estates/<int:id>", EstateDetail.as_view()),
    path("estates/<int:id>/admin", EstateFirstAdmin.as_view()),
    path("estate", MyEstate.as_view()),
    path("estate/public", PublicEstate.as_view()),
    # Sandbox estates
    path("estates/sandbox", sb.CreateSandbox.as_view()),
    path("estates/<int:id>/testers", sb.AddTester.as_view()),
    path("estates/<int:id>/reset", sb.PlatformResetSandbox.as_view()),
    path("sandbox", sb.SandboxInfo.as_view()),
    path("sandbox/outbox", sb.Outbox.as_view()),
    path("sandbox/whatsapp", sb.WhatsAppSimulator.as_view()),
    path("sandbox/ussd", sb.UssdSimulator.as_view()),
    path("sandbox/reset", sb.ResetSandbox.as_view()),
]
