from django.contrib import admin

from .models import MessageLog, WhatsAppSession


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ("wa_id", "state", "last_inbound_at", "updated_at")
    search_fields = ("wa_id",)


@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "wa_id", "direction", "ok")
    list_filter = ("direction", "ok")
    search_fields = ("wa_id", "message_id")
