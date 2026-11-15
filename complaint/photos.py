from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from smartEstateBackend.permissions import IsAdminOrGuard

from .models import Complain, ComplaintPhoto


class ComplaintPhotos(APIView):
    permission_classes = [IsAdminOrGuard]

    def get(self, request, id):
        complaint = get_object_or_404(Complain, pk=id)
        return Response([
            {"id": p.id, "url": f"complain/photos/{p.id}", "content_type": p.content_type, "created_at": p.created_at}
            for p in complaint.photos.all()
        ])


class ComplaintPhotoFile(APIView):
    """The image itself; staff only, so the frontend fetches it with the login token."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request, photo_id):
        photo = get_object_or_404(ComplaintPhoto, pk=photo_id)
        response = FileResponse(photo.image.open("rb"), content_type=photo.content_type)
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        return response
