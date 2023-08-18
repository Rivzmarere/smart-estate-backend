import math
from .models import Complain
from .serializer import ComplainReadSerializer, ComplainWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from .utilities import random_numbers,search_auth,search_home
# Create your views here.

class ComplainList(GenericAPIView):
    serializer_class = ComplainReadSerializer
    def get(self, request, format=None):
            complains = Complain.objects.all()
            serializer = ComplainReadSerializer(complains, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ComplainWriteSerializer(data=request.data)
            if serializer.is_valid():
                print('ndapinda')
                is_visit_valid = search_auth(request.data["stand_number"],request.data["resident_phone_number"])
                if (is_visit_valid == True):
                    home_address =search_home(request.data["stand_number"])
                    complain_code = random_numbers()
                    serializer.save(complain_code=complain_code,home=home_address["address"])
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                else:
                    message ={"Stand Number or Phone Numebr is Invalid"}
                    return Response(data=message,status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ComplainPaginated(GenericAPIView):
    serializer_class = ComplainReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        per_page = 5

        complains = Complain.objects.all()
        if sort =='asc':
            complains = complains.order_by('-date_created')
        
        total = complains.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ComplainReadSerializer(complains[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ComplainDetails(GenericAPIView):
    serializer_class = ComplainReadSerializer
    def getObject(self, id):
        try:
            return Complain.objects.get(pk=id)
        except Complain.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    def get(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ComplainReadSerializer(complain)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            complain = self.getObject(id)
            serializer = ComplainReadSerializer(complain, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            complain = self.getObject(id)
            complain.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)


