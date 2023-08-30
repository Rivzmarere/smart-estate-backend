import math
from .models import Home
from .serializer import HomeReadSerializer, HomeWriteSerializer,HomeStatusUpdateSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
# Create your views here.

class HomeList(GenericAPIView):
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
    serializer_class = HomeReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        search = request.GET.get('search')
        status_filter = request.GET.get('status')
        per_page = 5

        homes = Home.objects.all()
        if search:
            homes = homes.filter(Q(owner__name__icontains = search) | Q(stand__stand_number__icontains = search) | Q(resident__name__icontains = search) | Q(resident__surname__icontains = search) | Q(owner__surname__icontains = search) | Q(address__icontains = search))
        
        if status_filter:
            homes = homes.filter(home_status = status_filter)
            
        if sort =='asc':
            homes = homes.order_by('-date_created').filter(status=True)
        
        total = homes.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = HomeReadSerializer(homes[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class HomeDetails(GenericAPIView):
    serializer_class = HomeReadSerializer
    def getObject(self, id):
        try:
            return Home.objects.get(pk=id)
        except Home.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            home = self.getObject(id)
            serializer = HomeReadSerializer(home)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            home = self.getObject(id)
            serializer = HomeStatusUpdateSerializer(home, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            home = self.getObject(id)
            home.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


