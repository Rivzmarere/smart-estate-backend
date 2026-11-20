from smartEstateBackend.listing import flag, number, page, param, search
import math
from .models import Complain
from .serializer import ComplainReadSerializer, ComplainWriteSerializer,ComplainAssignUpdateSerializer,ComplainUpdateStatusSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from .utilities import random_numbers,search_auth,search_home
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import IsAdminOrGuard, IsAdminRole, PublicCreateStaffRead
from rest_framework.throttling import ScopedRateThrottle
# Create your views here.

class ComplainList(GenericAPIView):
    permission_classes = [PublicCreateStaffRead]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_booking"
    serializer_class = ComplainReadSerializer
    def get(self, request, format=None):
            complains = Complain.objects.all()
            serializer = ComplainReadSerializer(complains, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ComplainWriteSerializer(data=request.data)
            if serializer.is_valid():
                is_visit_valid = search_auth(request.data["stand_number"],request.data["resident_phone_number"])
                if (is_visit_valid == True):
                    home_address =search_home(request.data["stand_number"])
                    complain_code = random_numbers()
                    serializer.save(complain_code=complain_code,home=home_address["address"])
                    return Response({
                        "data":{
                            "visit_code":complain_code,
                            }
                        }, status=status.HTTP_201_CREATED)
                else:
                    message ={"Stand Number or Phone Numebr is Invalid"}
                    return Response(data=message,status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ComplainPaginated(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = ComplainReadSerializer
    def get(self, request, format=None):
        complaints = Complain.objects.filter(status=True).select_related("complaint_category", "compalint_status").order_by("-date_created")
        if param(request, "search"):
            complaints = search(complaints, param(request, "search"), ["complain_code", "stand_number", "home", "description", "complaint_category__name"])
        return page(request, complaints, ComplainReadSerializer)



class ComplainDetails(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ComplainReadSerializer
    def getObject(self, id):
        return get_object_or_404(Complain, pk=id)
        
    def get(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ComplainReadSerializer(complain)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ComplainReadSerializer(complain, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            complain = self.getObject(id)
            complain.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


class ComplainAssignDetails(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ComplainReadSerializer
    def getObject(self, id):
        return get_object_or_404(Complain, pk=id)
        
    def put(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ComplainAssignUpdateSerializer(complain, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class ComplainUpdateStatusDetails(GenericAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ComplainReadSerializer
    def getObject(self, id):
        return get_object_or_404(Complain, pk=id)
        
    def put(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ComplainUpdateStatusSerializer(complain, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



