from smartEstateBackend.listing import flag, number, page, param, search
import math
from .models import Resident
from .serializer import ResidentReadSerializer, ResidentWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import StaffReadAdminWrite
# Create your views here.

class ResidentList(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ResidentReadSerializer
    def get(self, request, format=None):
            residents = Resident.objects.all()
            serializer = ResidentReadSerializer(residents, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ResidentWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ResidentPaginated(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ResidentReadSerializer
    def get(self, request, format=None):
        residents = Resident.objects.all().order_by("surname", "name", "id")
        if param(request, "search"):
            residents = search(residents, param(request, "search"), ["name", "surname", "id_number", "phone_number1", "phone_number2", "email"])
        active = flag(param(request, "status"))
        if active is not None:
            residents = residents.filter(status=active)
        return page(request, residents, ResidentReadSerializer)



class ResidentDetails(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ResidentReadSerializer
    def getObject(self, id):
        return get_object_or_404(Resident, pk=id)
        
    def get(self, request, id, format=None):
            resident = self.getObject(id)
            serializer = ResidentReadSerializer(resident)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            resident = self.getObject(id)
            serializer = ResidentReadSerializer(resident, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            resident = self.getObject(id)
            resident.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


