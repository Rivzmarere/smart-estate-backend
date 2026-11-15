from rest_framework import serializers

from authentication.serializer import UserSummarySerializer

from .models import Notice


class NoticePublicSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Notice
        fields = ["id", "title", "body", "category", "category_label", "pinned", "publish_at", "expires_at"]


class NoticeAdminSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    created_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Notice
        fields = [
            "id", "title", "body", "category", "category_label", "pinned", "published",
            "publish_at", "expires_at", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        publish_at = attrs.get("publish_at", getattr(self.instance, "publish_at", None))
        expires_at = attrs.get("expires_at", getattr(self.instance, "expires_at", None))
        if publish_at and expires_at and expires_at <= publish_at:
            raise serializers.ValidationError({"expires_at": "Must be after the publish time."})
        return attrs
