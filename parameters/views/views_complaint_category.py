import math
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.serializers.serializer_complaint_category import ComplaintCategoryReadSerializer, ComplaintCategoryWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from smartEstateBackend.permissions import SharedListPermission
# Create your views here.

class ComplaintCategorysList(GenericAPIView):
    permission_classes = [SharedListPermission]
    serializer_class = ComplaintCategoryReadSerializer
    def get(self, request, format=None):
            complaint_category = ComplaintCategory.objects.filter(status=True)
            serializer = ComplaintCategoryReadSerializer(complaint_category, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = ComplaintCategoryWriteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ComplaintCategorysPaginated(GenericAPIView):
    permission_classes = [SharedListPermission]
    serializer_class = ComplaintCategoryReadSerializer
    def get(self, request, format=None):
        sort = 'asc'
        page = int(request.GET.get('page',1))
        status_filter = request.GET.get('status')
        search = request.GET.get('search')
        per_page = 20

        complaint_category = ComplaintCategory.objects.all()
        
        if search:
            complaint_category = complaint_category.filter(name__icontains = search)
              
        if status_filter:
            complaint_category = complaint_category.filter(status = status_filter)
            
        if sort =='asc':
            complaint_category = complaint_category.order_by('-date_created')
        
        total = complaint_category.count()
        start = (page - 1) * per_page
        end = page * per_page

        serializer = ComplaintCategoryReadSerializer(complaint_category[start:end], many=True)
        return Response({
            'data':serializer.data,
            'total': total,
            'page':page,
            'last_page':math.ceil(total / per_page)

        })


class ComplaintCategorysDetails(GenericAPIView):
    permission_classes = [SharedListPermission]
    serializer_class = ComplaintCategoryReadSerializer
    def getObject(self, id):
        return get_object_or_404(ComplaintCategory, pk=id)
        
    def get(self, request, id, format=None):
            complaint_category = self.getObject(id)
            serializer = ComplaintCategoryReadSerializer(complaint_category)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id, format=None):
            complaint_category = self.getObject(id)
            serializer = ComplaintCategoryReadSerializer(complaint_category, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, id, format=None):
            complaint_category = self.getObject(id)
            # Shared by every estate and linked to their records: archive, never delete.
            complaint_category.status = False
            complaint_category.save(update_fields=["status"])
            return Response(status=status.HTTP_204_NO_CONTENT)


