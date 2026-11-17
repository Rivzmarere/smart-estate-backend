from django.urls import path

from . import org_views as org
from . import sandbox_views as sb
from .views import EstateDetail, EstateFirstAdmin, Estates, MyEstate, PublicEstate

urlpatterns = [
    path("estates", Estates.as_view()),
    path("estates/<int:id>", EstateDetail.as_view()),
    path("estates/<int:id>/admin", EstateFirstAdmin.as_view()),
    path("estate", MyEstate.as_view()),
    path("estate/public", PublicEstate.as_view()),
    path("estate/context", org.Workspace.as_view()),
    # Managing agents and landlords
    path("organisations", org.Organisations.as_view()),
    path("organisations/<int:id>", org.OrganisationDetail.as_view()),
    path("organisations/<int:id>/admin", org.OrganisationFirstAdmin.as_view()),
    path("organisation", org.MyOrganisation.as_view()),
    path("organisation/estates", org.MyEstates.as_view()),
    path("organisation/overview", org.Overview.as_view()),
    path("organisation/staff", org.Staff.as_view()),
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
