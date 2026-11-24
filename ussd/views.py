"""
The USSD gateway calls this for every screen. Request (form-encoded, the
format used by Africa's Talking and most aggregators):
    sessionId, serviceCode, phoneNumber, text   (answers so far, joined by "*")
Response: plain text starting "CON " (wait for an answer) or "END " (finish).

Other gateways need only a small adapter around ussd.menu.handle().
The URL carries USSD_SECRET so only the gateway can call it; with no secret
set the endpoint does not exist.
"""

import hmac
import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .menu import handle

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def gateway(request, secret):
    expected = settings.USSD_SECRET
    if not expected or not hmac.compare_digest(secret, expected):
        raise Http404
    phone = request.POST.get("phoneNumber", "")
    text = request.POST.get("text", "")
    try:
        keep_open, message = handle(phone, text)
    except Exception:
        logger.exception("USSD failed for session %s", request.POST.get("sessionId"))
        keep_open, message = False, "Sorry, something went wrong. Please try again later."
    return HttpResponse(("CON " if keep_open else "END ") + message, content_type="text/plain; charset=utf-8")
