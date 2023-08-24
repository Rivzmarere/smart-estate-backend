import math
from parameters.models.models_visit_status import VisitStatus
from parameters.serializers.serializer_visit_status import VisitStatusReadSerializer, VisitStatusWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class VisitStatusList(GenericAPIView):
    serializer_class = VisitStatusReadSerializer
    def get(self, request, format=None):
            visit_status = VisitStatus.objects.all()
            serializer = VisitStatusReadSerializer(visit_status, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = VisitStatusWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class VisitStatusPaginated(GenericAPIView):
    serializer_class = VisitStatusReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        visit_status = VisitStatus.objects.all()
        
        if search:
            visit_status = visit_status.filter(name__icontains = search)
              
        if status_filter:
            visit_status = visit_status.filter(status = status_filter)
        if sort =='asc':
           visit_status = visit_status.order_by('-date_created')
        
        total =visit_status.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = VisitStatusReadSerializer(visit_status[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class VisitStatusDetails(GenericAPIView):
    serializer_class = VisitStatusReadSerializer
    def getObject(self, id):
        try:
            return VisitStatus.objects.get(pk=id)
        except VisitStatus.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            visit_status = self.getObject(id)
            serializer = VisitStatusReadSerializer(visit_status)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            visit_status = self.getObject(id)
            serializer = VisitStatusReadSerializer(visit_status, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            visit_status = self.getObject(id)
            visit_status.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


