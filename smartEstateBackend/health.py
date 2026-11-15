from django.db import connection
from django.http import JsonResponse


def health(request):
    """For the container health check and uptime monitors: is the API up and the database reachable?"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "database unavailable"}, status=503)
