import math
from .models import Provider
from .serializer import ProviderReadSerializer, ProviderWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.

class ProviderList(GenericAPIView):
    serializer_class = ProviderReadSerializer
    def get(self, request, format=None):
            providers = Provider.objects.all()
            serializer = ProviderReadSerializer(providers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ProviderWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ProviderPaginated(GenericAPIView):
    serializer_class = ProviderReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        providers = Provider.objects.all()
        if sort =='asc':
            providers = providers.order_by('-date_created')
        
        total = providers.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ProviderReadSerializer(providers[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ProviderDetails(GenericAPIView):
    serializer_class = ProviderReadSerializer
    def getObject(self, id):
        try:
            return Provider.objects.get(pk=id)
        except Provider.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            provider = self.getObject(id)
            serializer = ProviderReadSerializer(provider)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            provider = self.getObject(id)
            serializer = ProviderReadSerializer(provider, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            provider = self.getObject(id)
            provider.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


