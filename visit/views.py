from smartEstateBackend.listing import flag, number, page, param, search
import math

from django.utils import timezone
from .models import Visit
from .serializer import VisitBookOutSerializer, VisitBookinSerializer, VisitReadSerializer, VisitWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from .messaging import notify_visitor_arrived, send_code_to_visitor
from .utilities import random_numbers,search_auth,search_home
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import IsAdminOrGuard, PublicCreateStaffRead
from rest_framework.throttling import ScopedRateThrottle
# Create your views here.

class VisitList(GenericAPIView):
    permission_classes = [PublicCreateStaffRead]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_booking"
    serializer_class = VisitReadSerializer
    def get(self, request, format=None):
            visits = Visit.objects.all()
            serializer = VisitReadSerializer(visits, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = VisitWriteSerializer(data=request.data)
            if serializer.is_valid():
                is_visit_valid = search_auth(request.data["stand_number"],request.data["resident_phone_number"])
                if (is_visit_valid == True):
                    home_address =search_home(request.data["stand_number"])
                    visit_code = random_numbers()
                    visit = serializer.save(visit_code=visit_code,home=home_address["address"])
                    sms_sent = send_code_to_visitor(visit)
                    return Response({
                        "data":{
                            "visit_code":visit_code,
                            "Visitor_name":request.data["visitor_name"],
                            "sms_sent": sms_sent,
                            }
                        }, status=status.HTTP_201_CREATED)
                else:
                    message ={"Stand Number or Phone Numebr is Invalid"}
                    return Response(data=message,status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class VisitPaginated(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = VisitReadSerializer
    def get(self, request, format=None):
        visits = Visit.objects.filter(status=True).order_by("-date_created")
        if param(request, "search"):
            visits = search(visits, param(request, "search"), ["visitor_name", "visit_code", "stand_number", "home", "visitor_vehicle_reg_number"])
        transport = number(param(request, "transport-filter"))
        if transport:
            visits = visits.filter(transport_type_id=transport)
        visit_status = number(param(request, "status-filter"))
        if visit_status:
            visits = visits.filter(visit_status_id=visit_status)
        return page(request, visits, VisitReadSerializer)



class VisitDetails(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = VisitReadSerializer
    def getObject(self, id):
        return get_object_or_404(Visit, pk=id)
        
    def get(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitReadSerializer(visit)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitReadSerializer(visit, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            visit = self.getObject(id)
            visit.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)



class VisitBookInUpdateDetails(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = VisitReadSerializer
    def getObject(self, id):
        return get_object_or_404(Visit, pk=id)
        
    def put(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitBookinSerializer(visit, data=request.data)
            if serializer.is_valid():
                visit = serializer.save(
                    authorized_by=request.user,
                    date_arrived=serializer.validated_data.get("date_arrived") or timezone.now(),
                )
                notify_visitor_arrived(visit)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        


class VisitBookOutUpdateDetails(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = VisitReadSerializer
    def getObject(self, id):
        return get_object_or_404(Visit, pk=id)
        
    def put(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitBookOutSerializer(visit, data=request.data)
            if serializer.is_valid():
                serializer.save(status=False, date_depature=timezone.now())
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

