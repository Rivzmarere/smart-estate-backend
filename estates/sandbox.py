"""
Sandbox estates: a full copy of the system for testers, safe to play with.

While working for a sandbox estate:
  * SMS and WhatsApp messages are stored as SandboxMessage (the Outbox), not sent;
  * Paynow is simulated: a payment is "approved" a few seconds after it starts
    (numbers ending in 3333 cancel, like Paynow's own test numbers);
  * portal sign-in codes are shown on screen.
Sandbox estates are left out of WhatsApp/USSD lookups for real numbers.
"""

from .context import in_sandbox


def whatsapp_text(payload):
    """Readable text for a captured WhatsApp message."""
    kind = payload.get("type")
    if kind == "text":
        return payload["text"]["body"]
    if kind == "interactive":
        inter = payload["interactive"]
        lines = [inter.get("body", {}).get("text", "")]
        action = inter.get("action", {})
        for b in action.get("buttons", []):
            lines.append(f"[{b['reply']['title']}]")
        for section in action.get("sections", []):
            for row in section.get("rows", []):
                lines.append(f"• {row['title']}" + (f" ({row['description']})" if row.get("description") else ""))
        return "\n".join(lines)
    if kind == "template":
        t = payload["template"]
        params = [p.get("text", "") for c in t.get("components", []) if c.get("type") == "body" for p in c.get("parameters", [])]
        return f"[template {t.get('name')}] " + " | ".join(params)
    return str(payload)


def capture(channel, to, text, payload=None):
    """Store an outgoing message instead of sending it, if we are in a sandbox. Returns True if captured."""
    if not in_sandbox():
        return False
    from .models import SandboxMessage

    SandboxMessage.objects.create(channel=channel, to=str(to), text=text[:4000], payload=payload or {})
    return True
