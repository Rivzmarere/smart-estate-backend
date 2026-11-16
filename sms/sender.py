"""
Send SMS through a pluggable backend.

SMS_BACKEND (environment variable):
  console  - default; nothing leaves the server, messages go to SmsLog and OUTBOX
  twilio   - Twilio REST API (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, SMS_SENDER)

A local Zimbabwean gateway (much cheaper per message than Twilio) can be added as
another backend function once a provider is chosen; only send_sms() is called
from the rest of the code.

Only Zimbabwean mobile numbers (+263 7x) are accepted, so a public form can
never be used to send SMS abroad.
"""

import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from .models import SmsLog

logger = logging.getLogger(__name__)

OUTBOX = []  # console backend; tests read this

MAX_LENGTH = 459  # three SMS segments


def zimbabwe_mobile(phone):
    """
    Return the number as +2637XXXXXXXX if it is a Zimbabwean mobile number, else None.
    Accepts 0772 111 111, 772111111, 263772111111, +263 77 211 1111.
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("263"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if re.fullmatch(r"7[1378]\d{7}", digits):
        return "+263" + digits
    return None


def _console(to, message):
    OUTBOX.append({"to": to, "message": message})
    logger.info("SMS (console) to %s: %s", to, message)
    return True, "", ""


def _twilio(to, message):
    sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": settings.SMS_SENDER, "Body": message}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read() or b"{}")
        return True, result.get("sid", ""), ""
    except urllib.error.HTTPError as exc:
        return False, "", exc.read().decode(errors="replace")[:2000]
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, "", str(exc)


BACKENDS = {"console": _console, "twilio": _twilio}


def send_sms(phone, message):
    """Send one SMS. Returns True on success. Never raises."""
    to = zimbabwe_mobile(phone)
    if not to:
        logger.info("Not sending SMS to non-Zimbabwean or invalid number %r", phone)
        return False
    message = message[:MAX_LENGTH]
    from estates.sandbox import capture

    if capture("sms", to, message):
        return True
    backend_name = settings.SMS_BACKEND
    backend = BACKENDS.get(backend_name, _console)
    try:
        ok, provider_id, error = backend(to, message)
    except Exception as exc:  # an SMS failure must never break a booking or the gate
        logger.exception("SMS backend %s failed", backend_name)
        ok, provider_id, error = False, "", str(exc)
    SmsLog.objects.create(to=to, message=message, backend=backend_name, ok=ok, provider_id=provider_id, error=error)
    if not ok:
        logger.warning("SMS to %s failed: %s", to, error)
    return ok
