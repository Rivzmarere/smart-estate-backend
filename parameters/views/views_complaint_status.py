import math
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.serializers.serializer_complaint_status import ComplaintStatusReadSerializer, ComplaintStatusWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class ComplaintStatusList(GenericAPIView):
    serializer_class = ComplaintStatusReadSerializer
    def get(self, request, format=None):
            complaint_status = ComplaintStatus.objects.all()
            serializer = ComplaintStatusReadSerializer(complaint_status, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ComplaintStatusWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ComplaintStatusPaginated(GenericAPIView):
    serializer_class = ComplaintStatusReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        complaint_status = ComplaintStatus.objects.all()
        if sort =='asc':
            complaint_status = complaint_status.order_by('-date_created')
        
        total = complaint_status.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ComplaintStatusReadSerializer(complaint_status[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ComplaintStatusDetails(GenericAPIView):
    serializer_class = ComplaintStatusReadSerializer
    def getObject(self, id):
        try:
            return ComplaintStatus.objects.get(pk=id)
        except ComplaintStatus.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            complaint_status = self.getObject(id)
            serializer = ComplaintStatusReadSerializer(complaint_status)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            complaint_status = self.getObject(id)
            serializer = ComplaintStatusReadSerializer(complaint_status, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            complaint_status = self.getObject(id)
            complaint_status.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


