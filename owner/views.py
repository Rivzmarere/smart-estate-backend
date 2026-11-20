from smartEstateBackend.listing import flag, number, page, param, search
import math
from .models import Owner
from .serializer import OwnerReadSerializer, OwnerWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import StaffReadAdminWrite
# Create your views here.

class OwnerList(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = OwnerReadSerializer
    def get(self, request, format=None):
            owners = Owner.objects.all()
            serializer = OwnerReadSerializer(owners, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = OwnerWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class OwnerPaginated(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = OwnerReadSerializer
    def get(self, request, format=None):
        owners = Owner.objects.all().order_by("surname", "name", "id")
        if param(request, "search"):
            owners = search(owners, param(request, "search"), ["name", "surname", "phone_number1", "phone_number2", "email", "id_number"])
        active = flag(param(request, "status"))
        if active is not None:
            owners = owners.filter(status=active)
        return page(request, owners, OwnerReadSerializer)



class OwnerDetails(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = OwnerReadSerializer
    def getObject(self, id):
        return get_object_or_404(Owner, pk=id)
        
    def get(self, request, id, format=None):
            owner = self.getObject(id)
            serializer = OwnerReadSerializer(owner)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            owner = self.getObject(id)
            serializer = OwnerReadSerializer(owner, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            owner = self.getObject(id)
            owner.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


