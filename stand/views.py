from smartEstateBackend.listing import form_data, flag, number, page, param, search
import math
from .models import Stand
from .serializer import StandReadSerializer, StandWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from smartEstateBackend.archive import archive_stand, respond
from rest_framework import status
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import StaffReadAdminWrite
# Create your views here.

class StandList(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = StandReadSerializer
    def get(self, request, format=None):
            stands = Stand.objects.filter(status=True).order_by("stand_number")
            serializer = StandReadSerializer(stands, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = StandWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class StandPaginated(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = StandReadSerializer
    def get(self, request, format=None):
        stands = Stand.objects.filter(status=True).select_related("stand_status").order_by("stand_number", "id")
        if param(request, "search"):
            stands = search(stands, param(request, "search"), ["stand_number"])
        stand_status = number(param(request, "stand-status", "status"))
        if stand_status:
            stands = stands.filter(stand_status_id=stand_status)
        return page(request, stands, StandReadSerializer)



class StandDetails(GenericAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = StandReadSerializer
    def getObject(self, id):
        return get_object_or_404(Stand, pk=id)
        
    def get(self, request, id, format=None):
            stand = self.getObject(id)
            serializer = StandReadSerializer(stand)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            stand = self.getObject(id)
            # Every field on the form is saved (links like gender, owner or resident included); fields not sent stay as they are.
            serializer = StandWriteSerializer(stand, data=form_data(request, Stand), partial=True)
            if serializer.is_valid():
                serializer.save()
                stand.refresh_from_db()
                return Response(StandReadSerializer(stand).data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            stand = self.getObject(id)
            return respond(stand, archive_stand)


