import math
from .models import Owner
from .serializer import OwnerReadSerializer, OwnerWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class OwnerList(GenericAPIView):
    serializer_class = OwnerReadSerializer
    def get(self, request, format=None):
            owners = Owner.objects.all()
            serializer = OwnerReadSerializer(owners, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = OwnerWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class OwnerPaginated(GenericAPIView):
    serializer_class = OwnerReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        owners = Owner.objects.all()
        if sort =='asc':
            owners = owners.order_by('-dateCreated')
        
        total = owners.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = OwnerReadSerializer(owners[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class OwnerDetails(GenericAPIView):
    serializer_class = OwnerReadSerializer
    def getObject(self, id):
        try:
            return Owner.objects.get(pk=id)
        except Owner.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            owner = self.getObject(id)
            serializer = OwnerReadSerializer(owner)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            owner = self.getObject(id)
            serializer = OwnerReadSerializer(owner, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            owner = self.getObject(id)
            owner.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


