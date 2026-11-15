from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from smartEstateBackend.permissions import IsAdminOrGuard, IsAdminRole

from .models import Conversation, EmergencyAlert
from .services import close_conversation, office_reply, tell_resident_about_alert


def person(user):
    return (user.get_full_name() or user.username) if user else ""


class AlertSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    phone = serializers.SerializerMethodField()
    acknowledged_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EmergencyAlert
        fields = [
            "id", "stand_number", "address", "resident_name", "phone", "kind", "kind_label", "details", "status",
            "status_label", "sms_sent_to", "acknowledged_by_name", "acknowledged_at", "resolved_by_name", "resolved_at",
            "created_at",
        ]

    def get_phone(self, alert):
        digits = "".join(ch for ch in alert.wa_id if ch.isdigit())
        return "0" + digits[3:] if digits.startswith("263") else digits

    def get_acknowledged_by_name(self, alert):
        return person(alert.acknowledged_by)

    def get_resolved_by_name(self, alert):
        return person(alert.resolved_by)


class Alerts(APIView):
    """Unresolved alerts, plus those resolved in the last 24 hours."""

    permission_classes = [IsAdminOrGuard]

    def get(self, request):
        since = timezone.now() - timedelta(hours=24)
        alerts = EmergencyAlert.objects.exclude(status=EmergencyAlert.RESOLVED, resolved_at__lt=since).select_related(
            "acknowledged_by", "resolved_by"
        )[:50]
        return Response(AlertSerializer(alerts, many=True).data)


class AlertAction(APIView):
    """POST .../acknowledge or .../resolve"""

    permission_classes = [IsAdminOrGuard]
    action = None

    def post(self, request, id):
        alert = get_object_or_404(EmergencyAlert, pk=id)
        now = timezone.now()
        if self.action == "acknowledge":
            if alert.status != EmergencyAlert.OPEN:
                return Response(AlertSerializer(alert).data)
            alert.status, alert.acknowledged_by, alert.acknowledged_at = EmergencyAlert.ACKNOWLEDGED, request.user, now
            alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])
        else:
            if alert.status == EmergencyAlert.RESOLVED:
                return Response(AlertSerializer(alert).data)
            if not alert.acknowledged_at:
                alert.acknowledged_by, alert.acknowledged_at = request.user, now
            alert.status, alert.resolved_by, alert.resolved_at = EmergencyAlert.RESOLVED, request.user, now
            alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "resolved_by", "resolved_at"])
        tell_resident_about_alert(alert)
        return Response(AlertSerializer(alert).data)


# ---------------------------------------------------------------- office inbox

def conversation_row(c):
    last = c.messages.order_by("-created_at").first()
    return {
        "id": c.id, "stand_number": c.stand_number, "address": c.address, "resident_name": c.resident_name,
        "phone": AlertSerializer().get_phone(c), "status": c.status, "unread": c.unread,
        "last_message_at": c.last_message_at, "created_at": c.created_at,
        "last_message": {"text": last.text[:120], "direction": last.direction} if last else None,
    }


def message_row(m):
    return {"id": m.id, "direction": m.direction, "text": m.text, "sent_by": person(m.sent_by), "delivered": m.delivered, "created_at": m.created_at}


class Conversations(APIView):
    """GET ?status=open|closed (default open)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        status = request.query_params.get("status", Conversation.OPEN)
        qs = Conversation.objects.filter(status=status).prefetch_related("messages")[:200]
        unread_total = sum(Conversation.objects.filter(status=Conversation.OPEN).values_list("unread", flat=True))
        return Response({"unread": unread_total, "conversations": [conversation_row(c) for c in qs]})


class ConversationDetail(APIView):
    """Opening a conversation marks it read."""

    permission_classes = [IsAdminRole]

    def get(self, request, id):
        conversation = get_object_or_404(Conversation, pk=id)
        if conversation.unread:
            conversation.unread = 0
            conversation.save(update_fields=["unread"])
        return Response({**conversation_row(conversation), "messages": [message_row(m) for m in conversation.messages.select_related("sent_by")]})


class ReplySerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, trim_whitespace=True)


class ConversationReply(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, id):
        conversation = get_object_or_404(Conversation.objects.select_related("home__estate"), pk=id)
        serializer = ReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = office_reply(conversation, serializer.validated_data["text"], request.user)
        body = message_row(message)
        if not message.delivered:
            body["warning"] = (
                "WhatsApp did not deliver this: the resident has not written in the last 24 hours. "
                f"Please phone them on {conversation_row(conversation)['phone']}."
            )
        return Response(body, status=201)


class ConversationClose(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, id):
        conversation = get_object_or_404(Conversation, pk=id)
        if conversation.status != Conversation.CLOSED:
            close_conversation(conversation, request.user)
        return Response(conversation_row(conversation))
