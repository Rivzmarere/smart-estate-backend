"""
Thin client for the Meta WhatsApp Cloud API.

Configuration (environment variables, see .env.example):
  WHATSAPP_TOKEN            permanent or test access token
  WHATSAPP_PHONE_NUMBER_ID  the sending number's ID from the Meta app dashboard
  WHATSAPP_API_VERSION      Graph API version, e.g. v23.0

When WHATSAPP_DRY_RUN is true (default in DEBUG and in tests) nothing is sent;
messages are recorded in OUTBOX and the MessageLog instead.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from .models import MessageLog

logger = logging.getLogger(__name__)

# Messages "sent" while in dry-run mode, newest last. Tests read this.
OUTBOX = []

# WhatsApp interactive message limits.
BUTTON_TITLE_MAX = 20
ROW_TITLE_MAX = 24
ROW_DESCRIPTION_MAX = 72
MAX_BUTTONS = 3
MAX_ROWS = 10


def _cut(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _send(wa_id, payload):
    body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": wa_id, **payload}
    if settings.WHATSAPP_DRY_RUN:
        OUTBOX.append(body)
        MessageLog.objects.create(wa_id=wa_id, direction=MessageLog.OUTBOUND, payload=body)
        return True

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    ok = True
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        ok = False
        result = {"error": exc.read().decode(errors="replace")[:2000], "status": exc.code}
        logger.warning("WhatsApp send failed to %s: %s", wa_id, result)
    except (urllib.error.URLError, TimeoutError) as exc:
        ok = False
        result = {"error": str(exc)}
        logger.warning("WhatsApp unreachable sending to %s: %s", wa_id, exc)

    message_id = None
    if ok:
        messages = result.get("messages") or [{}]
        message_id = messages[0].get("id")
    MessageLog.objects.create(
        wa_id=wa_id, direction=MessageLog.OUTBOUND, message_id=message_id, payload={"request": body, "response": result}, ok=ok
    )
    return ok


def send_text(wa_id, text):
    return _send(wa_id, {"type": "text", "text": {"body": text, "preview_url": False}})


def send_buttons(wa_id, text, buttons):
    """buttons: list of (id, title), at most 3."""
    return _send(
        wa_id,
        {
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": bid, "title": _cut(title, BUTTON_TITLE_MAX)}}
                        for bid, title in buttons[:MAX_BUTTONS]
                    ]
                },
            },
        },
    )


def send_list(wa_id, text, button_label, rows, section_title="Options"):
    """rows: list of (id, title, description or None), at most 10."""
    return _send(
        wa_id,
        {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": text},
                "action": {
                    "button": _cut(button_label, BUTTON_TITLE_MAX),
                    "sections": [
                        {
                            "title": _cut(section_title, ROW_TITLE_MAX),
                            "rows": [
                                {"id": rid, "title": _cut(title, ROW_TITLE_MAX), **({"description": _cut(desc, ROW_DESCRIPTION_MAX)} if desc else {})}
                                for rid, title, desc in rows[:MAX_ROWS]
                            ],
                        }
                    ],
                },
            },
        },
    )


def send_template(wa_id, name, parameters, language="en", button_payloads=()):
    """
    Approved template message; required to message someone outside the 24-hour window.
    button_payloads: one payload per quick-reply button in the template, in order.
    """
    components = [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in parameters]}]
    for index, payload in enumerate(button_payloads):
        components.append(
            {"type": "button", "sub_type": "quick_reply", "index": str(index), "parameters": [{"type": "payload", "payload": payload}]}
        )
    return _send(
        wa_id,
        {"type": "template", "template": {"name": name, "language": {"code": language}, "components": components}},
    )


# Media a resident sends us (repair photos).
MAX_MEDIA_BYTES = 5 * 1024 * 1024
DRY_RUN_MEDIA = {}  # media_id -> (bytes, mime type), for tests


def _get(url, timeout=15):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
    return urllib.request.urlopen(request, timeout=timeout)


def download_media(media_id):
    """(bytes, mime type) for an inbound media ID, or (None, None). Never raises."""
    if settings.WHATSAPP_DRY_RUN:
        return DRY_RUN_MEDIA.get(media_id, (None, None))
    try:
        with _get(f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{media_id}") as response:
            info = json.loads(response.read() or b"{}")
        url = info.get("url", "")
        if not url.startswith("https://"):
            return None, None
        if int(info.get("file_size") or 0) > MAX_MEDIA_BYTES:
            return None, None
        with _get(url, timeout=30) as response:
            data = response.read(MAX_MEDIA_BYTES + 1)
        if len(data) > MAX_MEDIA_BYTES:
            return None, None
        return data, info.get("mime_type", "")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Could not download WhatsApp media %s: %s", media_id, exc)
        return None, None
