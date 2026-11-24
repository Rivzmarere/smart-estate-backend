from smartEstateBackend.listing import form_data, flag, number, page, param, search
import math
from .models import Resident
from .serializer import ResidentReadSerializer, ResidentWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from smartEstateBackend.archive import archive_resident, respond
from rest_framework import status
from django.db.models import Q
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import StaffReadAdminWrite
# Create your views here.

class ResidentList(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ResidentReadSerializer
    def get(self, request, format=None):
            residents = Resident.objects.filter(status=True).order_by("surname", "name")
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
        if active is None:
            active = True  # removed (archived) people show only when asked for
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
            # Every field on the form is saved (links like gender, owner or resident included); fields not sent stay as they are.
            serializer = ResidentWriteSerializer(resident, data=form_data(request, Resident), partial=True)
            if serializer.is_valid():
                serializer.save()
                resident.refresh_from_db()
                return Response(ResidentReadSerializer(resident).data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            resident = self.getObject(id)
            return respond(resident, archive_resident)


