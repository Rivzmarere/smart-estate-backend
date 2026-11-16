"""Sandbox tools: who to be, what would have been sent, and a phone simulator for WhatsApp and USSD."""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from sms.sender import zimbabwe_mobile
from smartEstateBackend.permissions import ROLE_ADMIN, ROLE_GUARD, is_admin, is_staff_member

from . import sandbox_seed
from .context import ALL, current_estate, use_estate
from .models import Estate, SandboxMessage
from .views import IsPlatformStaff


def sandbox_estate():
    estate = current_estate()
    return estate if estate not in (None, ALL) and estate.sandbox else None


class InSandbox(BasePermission):
    message = "Sandbox tools only work in a sandbox estate."

    def has_permission(self, request, view):
        return is_staff_member(request.user) and sandbox_estate() is not None


def outbox_row(m):
    return {"id": m.id, "channel": m.channel, "to": m.to, "text": m.text, "created_at": m.created_at}


class SandboxInfo(APIView):
    permission_classes = [InSandbox]

    def get(self, request):
        estate = sandbox_estate()
        return Response({"estate": {"name": estate.name, "slug": estate.slug}, "people": sandbox_seed.demo_people(estate)})


class Outbox(APIView):
    """GET ?to=<number>&after=<id>"""

    permission_classes = [InSandbox]

    def get(self, request):
        qs = SandboxMessage.objects.all()
        if request.query_params.get("to"):
            qs = qs.filter(to__in=_spellings(request.query_params["to"]))
        if request.query_params.get("after", "").isdigit():
            qs = qs.filter(pk__gt=int(request.query_params["after"]))
        return Response([outbox_row(m) for m in qs[:200]])


def _spellings(phone):
    number = zimbabwe_mobile(phone) or phone
    digits = "".join(ch for ch in number if ch.isdigit())
    return {number, digits, "0" + digits[3:] if digits.startswith("263") else digits}


def _reply(m):
    """A captured bot message as the simulator shows it."""
    p = m.payload
    if p.get("type") == "interactive":
        inter = p["interactive"]
        action = inter.get("action", {})
        if "buttons" in action:
            options = [{"id": b["reply"]["id"], "title": b["reply"]["title"]} for b in action["buttons"]]
            return {"id": m.id, "kind": "buttons", "text": inter["body"]["text"], "options": options}
        rows = [{"id": r["id"], "title": r["title"], "description": r.get("description", "")} for s in action.get("sections", []) for r in s.get("rows", [])]
        return {"id": m.id, "kind": "list", "text": inter["body"]["text"], "button": action.get("button", "Choose"), "options": rows}
    return {"id": m.id, "kind": "text", "text": m.text}


class WhatsAppSimulator(APIView):
    """POST {phone, text} or {phone, choice}: what the bot replies, without Meta."""

    permission_classes = [InSandbox]

    def post(self, request):
        from whatsapp.bot import handle_message

        estate = sandbox_estate()
        phone = zimbabwe_mobile(request.data.get("phone"))
        if not phone:
            return Response({"phone": ["Enter a Zimbabwean mobile number."]}, status=400)
        wa_id = phone.lstrip("+")
        if request.data.get("choice"):
            message = {"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": str(request.data["choice"]), "title": ""}}}
        else:
            message = {"type": "text", "text": {"body": str(request.data.get("text") or "")[:1000]}}
        with use_estate(estate):
            last = SandboxMessage.objects.order_by("-id").values_list("id", flat=True).first() or 0
            handle_message(wa_id, message)
            replies = SandboxMessage.objects.filter(pk__gt=last, channel=SandboxMessage.WHATSAPP, to=wa_id).order_by("id")
        return Response({"replies": [_reply(m) for m in replies]})


class UssdSimulator(APIView):
    """POST {phone, text}: one USSD screen, as a gateway would get it."""

    permission_classes = [InSandbox]

    def post(self, request):
        from ussd.menu import handle

        with use_estate(sandbox_estate()):
            keep_open, message = handle(request.data.get("phone", ""), request.data.get("text", ""))
        return Response({"continue": keep_open, "message": message})


class ResetSandbox(APIView):
    """Put the sample data back as new (keeps everyone's logins)."""

    permission_classes = [InSandbox]

    def post(self, request):
        if not is_admin(request.user):
            return Response({"detail": "Only sandbox administrators can reset it."}, status=403)
        estate = sandbox_estate()
        sandbox_seed.wipe(estate)
        sandbox_seed.seed(estate, staff=request.user)
        return Response({"reset": True})


# ---------------------------------------------------------------- platform staff

class CreateSandbox(APIView):
    """POST {name}: a new sandbox estate with sample data and two logins (shown once)."""

    permission_classes = [IsPlatformStaff]

    def post(self, request):
        name = (request.data.get("name") or "").strip() or "Sandbox Estate"
        estate, logins = sandbox_seed.create_sandbox(name[:120])
        return Response({"id": estate.id, "slug": estate.slug, "name": estate.name,
                         "logins": [{"role": r, "username": u, "password": p} for r, u, p in logins]}, status=201)


class AddTester(APIView):
    """POST {role: Admin|Guard, label}: another login for a sandbox estate (password shown once)."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, id):
        estate = get_object_or_404(Estate, pk=id, sandbox=True)
        role = request.data.get("role", ROLE_ADMIN)
        if role not in (ROLE_ADMIN, ROLE_GUARD):
            return Response({"role": ["Admin or Guard."]}, status=400)
        label = "".join(ch for ch in str(request.data.get("label", "")).lower() if ch.isalnum())[:20]
        username, password = sandbox_seed.create_tester(estate, role, label)
        return Response({"role": role, "username": username, "password": password}, status=201)


class PlatformResetSandbox(APIView):
    permission_classes = [IsPlatformStaff]

    def post(self, request, id):
        estate = get_object_or_404(Estate, pk=id, sandbox=True)
        sandbox_seed.reset(estate)
        return Response({"reset": True})
