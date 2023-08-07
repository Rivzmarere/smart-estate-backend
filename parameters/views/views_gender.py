import math
from parameters.models.models_gender import Gender
from parameters.serializers.serializer_gender import GenderReadSerializer, GenderWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class GenderList(GenericAPIView):
    serializer_class = GenderReadSerializer
    def get(self, request, format=None):
            gender = Gender.objects.all()
            serializer = GenderReadSerializer(gender, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = GenderWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class GenderPaginated(GenericAPIView):
    serializer_class = GenderReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        gender = Gender.objects.all()
        if sort =='asc':
            gender = gender.order_by('-dateCreated')
        
        total = gender.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = GenderReadSerializer(gender[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class GenderDetails(GenericAPIView):
    serializer_class = GenderReadSerializer
    def getObject(self, id):
        try:
            return Gender.objects.get(pk=id)
        except Gender.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            gender = self.getObject(id)
            serializer = GenderReadSerializer(gender)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            gender = self.getObject(id)
            serializer = GenderReadSerializer(gender, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            gender = self.getObject(id)
            gender.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


