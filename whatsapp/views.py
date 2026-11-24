"""
Webhook endpoint for the Meta WhatsApp Cloud API.

GET  /whatsapp/webhook  Meta's one-time verification handshake
POST /whatsapp/webhook  incoming messages and delivery statuses
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import bot
from .models import MessageLog

logger = logging.getLogger(__name__)


def _valid_signature(request):
    secret = settings.WHATSAPP_APP_SECRET
    if not secret:
        # Only allowed while developing; production settings refuse to start without it.
        return settings.DEBUG
    header = request.headers.get("X-Hub-Signature-256", "")
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if not settings.WHATSAPP_ENABLED:
        return HttpResponse(status=404)

    if request.method == "GET":
        if (
            request.GET.get("hub.mode") == "subscribe"
            and settings.WHATSAPP_VERIFY_TOKEN
            and hmac.compare_digest(request.GET.get("hub.verify_token", ""), settings.WHATSAPP_VERIFY_TOKEN)
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponseForbidden("verification failed")

    if not _valid_signature(request):
        logger.warning("Rejected WhatsApp webhook with a bad signature")
        return HttpResponseForbidden("bad signature")

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                wa_id = message.get("from")
                message_id = message.get("id")
                if not wa_id:
                    continue
                # Meta retries deliveries; the unique message_id makes each one count once.
                try:
                    with transaction.atomic():
                        MessageLog.objects.create(wa_id=wa_id, direction=MessageLog.INBOUND, message_id=message_id, payload=message)
                except IntegrityError:
                    continue
                try:
                    bot.handle_message(wa_id, message)
                except Exception:
                    logger.exception("WhatsApp bot failed on message %s", message_id)
    # Always 200 so Meta does not keep retrying a message we have logged.
    return JsonResponse({"status": "ok"})
