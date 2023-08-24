import math
from parameters.models.models_provider_status import ProviderStatus
from parameters.serializers.serializer_provider_status import ProviderStatusReadSerializer, ProviderStatusWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class ProviderStatusList(GenericAPIView):
    serializer_class = ProviderStatusReadSerializer
    def get(self, request, format=None):
            provider_status = ProviderStatus.objects.all()
            serializer = ProviderStatusReadSerializer(provider_status, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ProviderStatusWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ProviderStatusPaginated(GenericAPIView):
    serializer_class = ProviderStatusReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 5

        provider_status = ProviderStatus.objects.all()
        
        if search:
            provider_status = provider_status.filter(name__icontains = search)
              
        if status_filter:
            provider_status = provider_status.filter(status = status_filter)
        if sort =='asc':
           provider_status = provider_status.order_by('-date_created')
        
        total =provider_status.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ProviderStatusReadSerializer(provider_status[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ProviderStatusDetails(GenericAPIView):
    serializer_class = ProviderStatusReadSerializer
    def getObject(self, id):
        try:
            return ProviderStatus.objects.get(pk=id)
        except ProviderStatus.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            provider_status = self.getObject(id)
            serializer = ProviderStatusReadSerializer(provider_status)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            provider_status = self.getObject(id)
            serializer = ProviderStatusReadSerializer(provider_status, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            provider_status = self.getObject(id)
            provider_status.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


