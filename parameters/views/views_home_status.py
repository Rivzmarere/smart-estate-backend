import math
from parameters.models.models_home_status import HomeStatus
from parameters.serializers.serializer_home_status import HomeStatusReadSerializer, HomeStatusWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import PublicReadAdminWrite
# Create your views here.

class HomeStatusList(GenericAPIView):
    permission_classes = [PublicReadAdminWrite]
    serializer_class = HomeStatusReadSerializer
    def get(self, request, format=None):
            home_status = HomeStatus.objects.all()
            serializer = HomeStatusReadSerializer(home_status, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = HomeStatusWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class HomeStatusPaginated(GenericAPIView):
    permission_classes = [PublicReadAdminWrite]
    serializer_class = HomeStatusReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        home_status = HomeStatus.objects.all()
        
        if search:
            home_status = home_status.filter(name__icontains = search)
              
        if status_filter:
            home_status = home_status.filter(status = status_filter)
        if sort =='asc':
            home_status = home_status.order_by('-date_created')
        
        total = home_status.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = HomeStatusReadSerializer(home_status[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class HomeStatusDetails(GenericAPIView):
    permission_classes = [PublicReadAdminWrite]
    serializer_class = HomeStatusReadSerializer
    def getObject(self, id):
        return get_object_or_404(HomeStatus, pk=id)
        
    def get(self, request, id, format=None):
            home_status = self.getObject(id)
            serializer = HomeStatusReadSerializer(home_status)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            home_status = self.getObject(id)
            serializer = HomeStatusReadSerializer(home_status, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            home_status = self.getObject(id)
            home_status.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


