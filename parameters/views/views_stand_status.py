import math
from parameters.models.models_stand_status import StandStatus
from parameters.serializers.serializer_stand_status import StandStatusReadSerializer, StandStatusWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class StandStatusList(GenericAPIView):
    serializer_class = StandStatusReadSerializer
    def get(self, request, format=None):
            stand_status = StandStatus.objects.all()
            serializer = StandStatusReadSerializer(stand_status, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = StandStatusWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class StandStatusPaginated(GenericAPIView):
    serializer_class = StandStatusReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        stand_status = StandStatus.objects.all()
        if sort =='asc':
           stand_status = stand_status.order_by('-dateCreated')
        
        total =stand_status.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = StandStatusReadSerializer(stand_status[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class StandStatusDetails(GenericAPIView):
    serializer_class = StandStatusReadSerializer
    def getObject(self, id):
        try:
            return StandStatus.objects.get(pk=id)
        except StandStatus.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            stand_status = self.getObject(id)
            serializer = StandStatusReadSerializer(stand_status)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            stand_status = self.getObject(id)
            serializer = StandStatusReadSerializer(stand_status, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            stand_status = self.getObject(id)
            stand_status.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


