from django.contrib import admin

from .models import Notice


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "pinned", "published", "publish_at", "expires_at")
    list_filter = ("category", "published", "pinned")
    search_fields = ("title", "body")
