import math
from parameters.models.models_provider_category import ProviderCategory
from parameters.serializers.serializer_provider_category import ProviderCategoryReadSerializer, ProviderCategoryWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class ProviderCategoryList(GenericAPIView):
    serializer_class = ProviderCategoryReadSerializer
    def get(self, request, format=None):
            provider_category = ProviderCategory.objects.all()
            serializer = ProviderCategoryReadSerializer(provider_category, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ProviderCategoryWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ProviderCategoryPaginated(GenericAPIView):
    serializer_class = ProviderCategoryReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        provider_category = ProviderCategory.objects.all()
        
        if search:
            provider_category = provider_category.filter(name__icontains = search)
              
        if status_filter:
            provider_category = provider_category.filter(status = status_filter)
        if sort =='asc':
           provider_category = provider_category.order_by('-date_created')
        
        total =provider_category.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ProviderCategoryReadSerializer(provider_category[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ProviderCategoryDetails(GenericAPIView):
    serializer_class = ProviderCategoryReadSerializer
    def getObject(self, id):
        try:
            return ProviderCategory.objects.get(pk=id)
        except ProviderCategory.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            provider_category = self.getObject(id)
            serializer = ProviderCategoryReadSerializer(provider_category)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            provider_category = self.getObject(id)
            serializer = ProviderCategoryReadSerializer(provider_category, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            provider_category = self.getObject(id)
            provider_category.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


