from smartEstateBackend.listing import flag, number, page, param, search
import math

from .models import WhiteList,WhiteListGuest
from .serializer import WhiteListBookInSerializer, WhiteListBookOutSerializer, WhiteListGuestReadSerializer, WhiteListGuestWriteSerializer, WhiteListReadSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from visit.utilities import random_numbers,search_auth,search_home
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import IsAdminOrGuard
# Create your views here.

class WhiteListGuestList(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = WhiteListGuestReadSerializer
    def get(self, request, format=None):
            white_list_guests = WhiteListGuest.objects.all()
            serializer = WhiteListGuestReadSerializer(white_list_guests, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = WhiteListGuestWriteSerializer(data=request.data)
            if serializer.is_valid():
                is_visit_valid = search_auth(request.data["stand_number"],request.data["resident_phone_number"])
                if (is_visit_valid == True):
                    home_address =search_home(request.data["stand_number"])
                    visit_code = random_numbers()
                    serializer.save(visit_code=visit_code,home=home_address["address"])
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                else:
                    message ={"Stand Number or Phone Numebr is Invalid"}
                    return Response(data=message,status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class WhiteListGuestPaginated(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = WhiteListGuestReadSerializer
    def get(self, request, format=None):
        guests = WhiteListGuest.objects.filter(status=True).order_by("-date_created")
        if param(request, "search"):
            guests = search(guests, param(request, "search"), ["visitor_name", "visit_code", "stand_number", "home", "visitor_vehicle_reg_number"])
        return page(request, guests, WhiteListGuestReadSerializer)



class WhiteListGuestDetails(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = WhiteListGuestReadSerializer
    def getObject(self, id):
        return get_object_or_404(WhiteListGuest, pk=id)
        
    def get(self, request, id, format=None):
            white_list_guest = self.getObject(id)
            serializer = WhiteListGuestReadSerializer(white_list_guest)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            white_list_guest = self.getObject(id)
            serializer = WhiteListGuestReadSerializer(white_list_guest, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            white_list_guest = self.getObject(id)
            white_list_guest.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)



class WhiteListPaginated(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = WhiteListReadSerializer
    def get(self, request, format=None):
        visits = WhiteList.objects.filter(status=True).select_related("white_list_guest").order_by("-date_arrived")
        if param(request, "search"):
            visits = search(visits, param(request, "search"), ["white_list_guest__visit_code", "white_list_guest__visitor_name", "white_list_guest__stand_number"])
        return page(request, visits, WhiteListReadSerializer)



class WhiteListBookInDetails(GenericAPIView):
    permission_classes = [IsAdminOrGuard]

    def post(self, request):
        serializer = WhiteListBookInSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(authorized_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WhiteListBookOutDetails(GenericAPIView):
    permission_classes = [IsAdminOrGuard]
    serializer_class = WhiteListReadSerializer
    def getObject(self, id):
        return get_object_or_404(WhiteList, pk=id)
        
    def put(self, request, id, format=None):
            white_list = self.getObject(id)
            serializer = WhiteListBookOutSerializer(white_list, data=request.data)
            if serializer.is_valid():
                serializer.save(status=False, date_depature=timezone.now())
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

