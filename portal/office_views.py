"""The estate office's side: approve household changes, see who belongs to each home."""

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from smartEstateBackend.permissions import IsAdminOrGuard, IsAdminRole

from . import household
from .models import HouseholdMember, HouseholdRequest


def office_row(r):
    return {
        "id": r.id, "home_id": r.home_id, "stand_number": r.home.stand.stand_number, "address": r.home.address,
        "kind": r.kind, "kind_label": r.get_kind_display(), "summary": household.describe(r), "details": r.details,
        "requested_by": household.local(r.requested_by_phone), "requested_by_role": r.requested_by_role,
        "status": r.status, "status_label": r.get_status_display(), "office_note": r.office_note,
        "decided_by": (r.decided_by.get_full_name() or r.decided_by.username) if r.decided_by else "",
        "created_at": r.created_at, "decided_at": r.decided_at,
    }


class OfficeRequests(APIView):
    """GET ?status=pending (default) | all."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = HouseholdRequest.objects.select_related("home__stand", "decided_by")
        if request.query_params.get("status", "pending") != "all":
            qs = qs.filter(status=HouseholdRequest.PENDING)
        return Response([office_row(r) for r in qs[:200]])


class DecideRequest(APIView):
    """POST {approve: bool, note?}"""

    permission_classes = [IsAdminRole]

    def post(self, request, id):
        req = get_object_or_404(HouseholdRequest.objects.select_related("home__stand", "home__estate"), pk=id)
        approve = request.data.get("approve")
        if not isinstance(approve, bool):
            return Response({"approve": "Send true or false."}, status=400)
        household.decide(req, approve, request.user, str(request.data.get("note") or ""))
        return Response(office_row(req))


class HomeHousehold(APIView):
    """Who belongs to a home: owner, main resident, members (guards see it too, for the gate)."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request, home_id):
        from home.models import Home

        home = get_object_or_404(Home.objects.select_related("owner", "resident"), pk=home_id)
        return Response({
            "owner": {"name": f"{home.owner.name} {home.owner.surname}", "phone": home.owner.phone_number1},
            "resident": {"name": f"{home.resident.name} {home.resident.surname}", "phone": home.resident.phone_number1} if home.resident else None,
            "members": [
                {"id": m.id, "name": m.full_name, "phone": household.local(m.phone), "relationship": m.get_relationship_display(),
                 "can_book_visitors": m.can_book_visitors}
                for m in HouseholdMember.objects.filter(home=home, active=True)
            ],
        })


class RemoveMember(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, member_id):
        member = get_object_or_404(HouseholdMember, pk=member_id)
        member.active = False
        member.save(update_fields=["active"])
        return Response({"id": member.id, "active": False})
