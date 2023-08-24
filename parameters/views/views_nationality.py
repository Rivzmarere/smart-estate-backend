import math
from parameters.models.models_nationality import Nationality
from parameters.serializers.serializer_nationality import NationalityReadSerializer, NationalityWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class NationalityList(GenericAPIView):
    serializer_class = NationalityReadSerializer
    def get(self, request, format=None):
            nationality = Nationality.objects.all()
            serializer = NationalityReadSerializer(nationality, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = NationalityWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class NationalityPaginated(GenericAPIView):
    serializer_class = NationalityReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        nationality = Nationality.objects.all()
        
        if search:
            nationality = nationality.filter(name__icontains = search)
              
        if status_filter:
            nationality = nationality.filter(status = status_filter)
        if sort =='asc':
           nationality =nationality.order_by('-date_created')
        
        total =nationality.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = NationalityReadSerializer(nationality[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class NationalityDetails(GenericAPIView):
    serializer_class = NationalityReadSerializer
    def getObject(self, id):
        try:
            return Nationality.objects.get(pk=id)
        except Nationality.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            nationality = self.getObject(id)
            serializer = NationalityReadSerializer(nationality)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            nationality = self.getObject(id)
            serializer = NationalityReadSerializer(nationality, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            nationality = self.getObject(id)
            nationality.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


