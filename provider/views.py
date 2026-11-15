import math
from .models import Provider
from .serializer import ProviderPublicSerializer, ProviderReadSerializer, ProviderWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import is_staff_member, PublicReadAdminWrite, StaffReadAdminWrite
# Create your views here.

class ProviderList(GenericAPIView):
    permission_classes = [PublicReadAdminWrite]
    serializer_class = ProviderReadSerializer

    def read_serializer(self):
        return ProviderReadSerializer if is_staff_member(self.request.user) else ProviderPublicSerializer
    def get(self, request, format=None):
            providers = Provider.objects.select_related("provider_category").order_by("name", "surname")
            if not is_staff_member(request.user):
                providers = providers.filter(status=True)  # residents only see providers in use
            serializer = self.read_serializer()(providers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ProviderWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ProviderPaginated(GenericAPIView):
    permission_classes = [PublicReadAdminWrite]
    serializer_class = ProviderReadSerializer

    def read_serializer(self):
        return ProviderReadSerializer if is_staff_member(self.request.user) else ProviderPublicSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        search = request.GET.get('search')
        per_page = 5

        providers = Provider.objects.all()
        if search:
            providers = providers.filter(Q(name__icontains = search) | Q(surname__icontains = search) | Q(provider_category__name__icontains = search))
        if sort =='asc':
            providers = providers.order_by('-date_created')
        
        total = providers.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = self.read_serializer()(providers[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ProviderDetails(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ProviderReadSerializer
    def getObject(self, id):
        return get_object_or_404(Provider, pk=id)
        
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


