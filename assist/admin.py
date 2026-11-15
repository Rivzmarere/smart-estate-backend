from django.contrib import admin

from .models import Conversation, ConversationMessage, EmergencyAlert

admin.site.register(EmergencyAlert)
admin.site.register(Conversation)
admin.site.register(ConversationMessage)
