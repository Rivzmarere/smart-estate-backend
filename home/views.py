from smartEstateBackend.listing import form_data, flag, number, page, param, search
import math
import re
from .models import Home
from .serializer import HomeReadSerializer, HomeWriteSerializer,HomeStatusUpdateSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from smartEstateBackend.archive import archive_home, respond
from rest_framework import status
from django.db.models import Q
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import IsAdminRole, StaffReadAdminWrite
# Create your views here.

class HomeList(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = HomeReadSerializer
    def get(self, request, format=None):
            homes = Home.objects.all()
            serializer = HomeReadSerializer(homes, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = HomeWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class HomePaginated(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = HomeReadSerializer
    def get(self, request, format=None):
        homes = Home.objects.filter(status=True).select_related("stand", "owner", "resident", "home_status").order_by("stand__stand_number", "id")
        if param(request, "search"):
            homes = search(homes, param(request, "search"), [
                "address", "stand__stand_number", "owner__name", "owner__surname", "resident__name", "resident__surname",
                "resident__phone_number1", "owner__phone_number1",
            ])
        home_status = number(param(request, "status"))
        if home_status:
            homes = homes.filter(home_status_id=home_status)
        return page(request, homes, HomeReadSerializer)



class HomeDetails(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = HomeReadSerializer
    def getObject(self, id):
        return get_object_or_404(Home, pk=id)
        
    def get(self, request, id, format=None):
            home = self.getObject(id)
            serializer = HomeReadSerializer(home)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            home = self.getObject(id)
            # Every field on the form is saved (links like gender, owner or resident included); fields not sent stay as they are.
            serializer = HomeWriteSerializer(home, data=form_data(request, Home), partial=True)
            if serializer.is_valid():
                serializer.save()
                home.refresh_from_db()
                return Response(HomeReadSerializer(home).data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            home = self.getObject(id)
            return respond(home, archive_home)




class HomeOverview(GenericAPIView):
    """GET home/<id>/overview: everything about one home on one page (administrators)."""

    permission_classes = [IsAdminRole]

    def get(self, request, id):
        from complaint.models import Complain
        from estates.org_views import CLOSED_REPAIR
        from levy.accounts import account
        from levy.models import Payment
        from portal.models import HouseholdMember, HouseholdRequest
        from visit.models import Visit
        from whitelist.models import WhiteListGuest

        home = get_object_or_404(Home.objects.select_related("stand", "owner", "resident", "home_status"), pk=id)
        number = home.stand.stand_number

        def person(p, phone_field="phone_number1"):
            if p is None:
                return None
            return {"id": p.id, "name": f"{p.name} {p.surname}".strip(), "phone": getattr(p, phone_field) or "",
                    "email": p.email or "", "id_number": p.id_number or ""}

        acc = account(home)
        last = (Payment.objects.filter(home=home, status=Payment.PAID).exclude(method__in=Payment.NOT_RECEIVED)
                .order_by("-paid_at").first())
        visits = Visit.objects.filter(stand_number=number).select_related("visit_status").order_by("-date_created")[:10]
        complaints = (Complain.objects.filter(stand_number=number, status=True)
                      .select_related("complaint_category", "compalint_status").order_by("-date_created")[:10])
        return Response({
            "id": home.id, "address": home.address, "stand": number, "active": home.status,
            "status": home.home_status.name if home.home_status_id else "",
            "owner": person(home.owner), "resident": person(home.resident),
            "household": [
                {"id": m.id, "name": f"{m.name} {m.surname}".strip(), "phone": m.phone, "relationship": m.get_relationship_display()}
                for m in HouseholdMember.objects.filter(home=home)
            ],
            "pending_requests": HouseholdRequest.objects.filter(home=home, status=HouseholdRequest.PENDING).count(),
            "account": {
                "balance": acc["balance"], "arrears": acc["arrears"], "credit": acc["credit"],
                "last_paid_at": last.paid_at if last else None, "last_paid_usd": last.amount_usd if last else None,
            },
            "visits": [
                {"id": v.id, "visitor": v.visitor_name, "vehicle": v.visitor_vehicle_reg_number or "", "booked": v.date_created,
                 "arrived": v.date_arrived, "left": v.date_depature, "status": v.visit_status.name if v.visit_status_id else ""}
                for v in visits
            ],
            "regulars": WhiteListGuest.objects.filter(stand_number=number).count(),
            "complaints": [
                {"id": c.id, "code": c.complain_code, "category": c.complaint_category.name, "status": c.compalint_status.name,
                 "description": c.description, "created": c.date_created,
                 "open": not re.search(CLOSED_REPAIR, c.compalint_status.name or "", re.I)}
                for c in complaints
            ],
        })
