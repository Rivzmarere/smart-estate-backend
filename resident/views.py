import math
from .models import Resident
from .serializer import ResidentReadSerializer, ResidentWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class ResidentList(GenericAPIView):
    serializer_class = ResidentReadSerializer
    def get(self, request, format=None):
            residents = Resident.objects.all()
            serializer = ResidentReadSerializer(residents, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ResidentWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ResidentPaginated(GenericAPIView):
    serializer_class = ResidentReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        residents = Resident.objects.all()
        if sort =='asc':
            residents = residents.order_by('-date_created')
        
        total = residents.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ResidentReadSerializer(residents[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ResidentDetails(GenericAPIView):
    serializer_class = ResidentReadSerializer
    def getObject(self, id):
        try:
            return Resident.objects.get(pk=id)
        except Resident.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            resident = self.getObject(id)
            serializer = ResidentReadSerializer(resident)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            resident = self.getObject(id)
            serializer = ResidentReadSerializer(resident, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            resident = self.getObject(id)
            resident.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


