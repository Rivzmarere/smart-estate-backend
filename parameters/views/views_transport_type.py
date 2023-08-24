import math
from parameters.models.models_transport_type import TransportType
from parameters.serializers.serializer_transport_type import TransportTypeReadSerializer, TransportTypeWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class TransportTypeList(GenericAPIView):
    serializer_class = TransportTypeReadSerializer
    def get(self, request, format=None):
            transport_type = TransportType.objects.all()
            serializer = TransportTypeReadSerializer(transport_type, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = TransportTypeWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class TransportTypePaginated(GenericAPIView):
    serializer_class = TransportTypeReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        transport_type = TransportType.objects.all()
        
        if search:
            transport_type = transport_type.filter(name__icontains = search)
              
        if status_filter:
            transport_type = transport_type.filter(status = status_filter)
        if sort =='asc':
           transport_type = transport_type.order_by('-date_created')
        
        total =transport_type.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = TransportTypeReadSerializer(transport_type[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class TransportTypeDetails(GenericAPIView):
    serializer_class = TransportTypeReadSerializer
    def getObject(self, id):
        try:
            return TransportType.objects.get(pk=id)
        except TransportType.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            transport_type = self.getObject(id)
            serializer = TransportTypeReadSerializer(transport_type)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            transport_type = self.getObject(id)
            serializer = TransportTypeReadSerializer(transport_type, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            transport_type = self.getObject(id)
            transport_type.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


