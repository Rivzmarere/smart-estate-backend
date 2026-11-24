from django.contrib import admin

from .models import SmsLog


@admin.register(SmsLog)
class SmsLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "to", "backend", "ok")
    list_filter = ("backend", "ok")
    search_fields = ("to",)
