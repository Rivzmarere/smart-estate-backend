import math

from .models import WhiteList,WhiteListGuest
from .serializer import WhiteListBookInSerializer, WhiteListBookOutSerializer, WhiteListGuestReadSerializer, WhiteListGuestWriteSerializer, WhiteListReadSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from visit.utilities import random_numbers,search_auth,search_home
from django.db.models import Q
# Create your views here.

class WhiteListGuestList(GenericAPIView):
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
    serializer_class = WhiteListGuestReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        search = request.GET.get('search')
        per_page = 5

        white_list_guests = WhiteListGuest.objects.all()
        if search:
            white_list_guests = white_list_guests.filter(Q(visitor_name__icontains = search) | Q(visit_code__icontains = search))
        
            
        if sort =='asc':
            white_list_guests = white_list_guests.order_by('-date_created').filter(status=True)
        
        
        total = white_list_guests.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = WhiteListGuestReadSerializer(white_list_guests[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class WhiteListGuestDetails(GenericAPIView):
    serializer_class = WhiteListGuestReadSerializer
    def getObject(self, id):
        try:
            return WhiteListGuest.objects.get(pk=id)
        except WhiteListGuest.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
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
    serializer_class = WhiteListReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        search = request.GET.get('search')
        per_page = 5

        white_list = WhiteList.objects.all()
        if search:
            white_list = white_list.filter(white_list_guest__visit_code__icontains = search)
        
            
        if sort =='asc':
            white_list = white_list.order_by('-date_arrived').filter(status=True)
        
        
        total = white_list.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = WhiteListReadSerializer(white_list[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })

class WhiteListBookInDetails(GenericAPIView):
   def post(self, request):
            serializer = WhiteListBookInSerializer(data=request.data)
            if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)
        


class WhiteListBookOutDetails(GenericAPIView):
    serializer_class = WhiteListReadSerializer
    def getObject(self, id):
        try:
            return WhiteList.objects.get(pk=id)
        except WhiteList.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def put(self, request, id, format=None):
            white_list = self.getObject(id)
            serializer = WhiteListBookOutSerializer(white_list, data=request.data)
            if serializer.is_valid():
                serializer.save(status=False)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

