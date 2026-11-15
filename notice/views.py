from rest_framework import generics
from rest_framework.permissions import AllowAny

from smartEstateBackend.permissions import IsAdminRole

from .models import Notice
from .serializer import NoticeAdminSerializer, NoticePublicSerializer


class PublicNotices(generics.ListAPIView):
    """Current notices for the resident portal (no login)."""

    permission_classes = [AllowAny]
    serializer_class = NoticePublicSerializer
    pagination_class = None

    def get_queryset(self):
        return Notice.objects.current()[:50]


class ManageNotices(generics.ListCreateAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = NoticeAdminSerializer
    pagination_class = None

    def get_queryset(self):
        return Notice.objects.select_related("created_by").all()[:500]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ManageNotice(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = NoticeAdminSerializer
    queryset = Notice.objects.all()
    lookup_url_kwarg = "id"
