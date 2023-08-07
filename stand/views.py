import math
from .models import Stand
from .serializer import StandReadSerializer, StandWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class StandList(GenericAPIView):
    serializer_class = StandReadSerializer
    def get(self, request, format=None):
            stands = Stand.objects.all()
            serializer = StandReadSerializer(stands, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = StandWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class StandPaginated(GenericAPIView):
    serializer_class = StandReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        stands = Stand.objects.all()
        if sort =='asc':
            stands = stands.order_by('-dateCreated')
        
        total = stands.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = StandReadSerializer(stands[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class StandDetails(GenericAPIView):
    serializer_class = StandReadSerializer
    def getObject(self, id):
        try:
            return Stand.objects.get(pk=id)
        except Stand.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            stand = self.getObject(id)
            serializer = StandReadSerializer(stand)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            stand = self.getObject(id)
            serializer = StandReadSerializer(stand, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            stand = self.getObject(id)
            stand.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


