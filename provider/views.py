from smartEstateBackend.listing import form_data, flag, number, page, param, search
import math
from .models import Provider
from .serializer import ProviderPublicSerializer, ProviderReadSerializer, ProviderWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from smartEstateBackend.archive import archive_simple, respond
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
        providers = Provider.objects.all().select_related("provider_category").order_by("-date_created")
        if param(request, "search"):
            providers = search(providers, param(request, "search"), ["name", "surname", "provider_category__name", "phone_number1", "address"])
        return page(request, providers, self.read_serializer())



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
            # Every field on the form is saved (links like gender, owner or resident included); fields not sent stay as they are.
            serializer = ProviderWriteSerializer(provider, data=form_data(request, Provider), partial=True)
            if serializer.is_valid():
                serializer.save()
                provider.refresh_from_db()
                return Response(ProviderReadSerializer(provider).data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            provider = self.getObject(id)
            return respond(provider, archive_simple, f"Removed service provider {provider.name} {provider.surname}")


