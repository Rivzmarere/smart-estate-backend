import math
from parameters.models.models_user_type import UserType
from parameters.serializers.serializer_user_type import UserTypeReadSerializer, UserTypeWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class UserTypeList(GenericAPIView):
    serializer_class = UserTypeReadSerializer
    def get(self, request, format=None):
            user_type = UserType.objects.all()
            serializer = UserTypeReadSerializer(user_type, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = UserTypeWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class UserTypePaginated(GenericAPIView):
    serializer_class = UserTypeReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        user_type = UserType.objects.all()
        
        if search:
            user_type = user_type.filter(name__icontains = search)
              
        if status_filter:
            user_type = user_type.filter(status = status_filter)
        if sort =='asc':
           user_type = user_type.order_by('-date_created')
        
        total =user_type.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = UserTypeReadSerializer(user_type[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class UserTypeDetails(GenericAPIView):
    serializer_class = UserTypeReadSerializer
    def getObject(self, id):
        try:
            return UserType.objects.get(pk=id)
        except UserType.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            user_type = self.getObject(id)
            serializer = UserTypeReadSerializer(user_type)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            user_type = self.getObject(id)
            serializer = UserTypeReadSerializer(user_type, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            user_type = self.getObject(id)
            user_type.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


