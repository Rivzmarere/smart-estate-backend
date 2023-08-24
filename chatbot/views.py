import math

from .utitls import chatResponse
from .serializer import ChatReadSerializer, ChatWriteSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status

# Create your views here.

class ChatList(GenericAPIView):
    serializer_class = ChatReadSerializer
    def post(self, request):
            serializer = ChatWriteSerializer(data=request.data)
            if serializer.is_valid():
                response = chatResponse(request.data["body"])
                return Response(response, status=status.HTTP_201_CREATED)
            return Response(status=status.HTTP_400_BAD_REQUEST)
