import math
from .models import Visit
from .serializer import VisitBookOutSerializer, VisitBookinSerializer, VisitReadSerializer, VisitWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from .utilities import random_numbers,search_auth,search_home
# Create your views here.

class VisitList(GenericAPIView):
    serializer_class = VisitReadSerializer
    def get(self, request, format=None):
            visits = Visit.objects.all()
            serializer = VisitReadSerializer(visits, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = VisitWriteSerializer(data=request.data)
            if serializer.is_valid():
                is_visit_valid = search_auth(request.data["stand_number"],request.data["resident_phone_number"])
                if (is_visit_valid == True):
                    home_address =search_home(request.data["stand_number"])
                    visit_code = random_numbers()
                    serializer.save(visit_code=visit_code,home=home_address["address"])
                    return Response({
                        "data":{
                            "visit_code":visit_code,
                            "Visitor_name":request.data["visitor_name"]
                            }
                        }, status=status.HTTP_201_CREATED)
                else:
                    message ={"Stand Number or Phone Numebr is Invalid"}
                    return Response(data=message,status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class VisitPaginated(GenericAPIView):
    serializer_class = VisitReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        search = request.GET.get('search')
        transport_filter = request.GET.get('transport-filter')
        status_filter = request.GET.get('status-filter')
        per_page = 5

        visits = Visit.objects.all()
        if search:
            visits = visits.filter(visitor_name__icontains = search)
        
        if transport_filter:
            visits = visits.filter(transport_type = transport_filter)
            
        if status_filter:
            visits = visits.filter(visit_status = status_filter)
            
        if sort =='asc':
            visits = visits.order_by('-date_created').filter(status=True)
        
        
        
        total = visits.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = VisitReadSerializer(visits[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class VisitDetails(GenericAPIView):
    serializer_class = VisitReadSerializer
    def getObject(self, id):
        try:
            return Visit.objects.get(pk=id)
        except Visit.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitReadSerializer(visit)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitReadSerializer(visit, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            visit = self.getObject(id)
            visit.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)



class VisitBookInUpdateDetails(GenericAPIView):
    serializer_class = VisitReadSerializer
    def getObject(self, id):
        try:
            return Visit.objects.get(pk=id)
        except Visit.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def put(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitBookinSerializer(visit, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        


class VisitBookOutUpdateDetails(GenericAPIView):
    serializer_class = VisitReadSerializer
    def getObject(self, id):
        try:
            return Visit.objects.get(pk=id)
        except Visit.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def put(self, request, id, format=None):
            visit = self.getObject(id)
            serializer = VisitBookOutSerializer(visit, data=request.data)
            if serializer.is_valid():
                serializer.save(status=False)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

