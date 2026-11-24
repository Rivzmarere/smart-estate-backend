from django.urls import path

from .views import AlertAction, Alerts, ConversationClose, ConversationDetail, ConversationReply, Conversations

urlpatterns = [
    path("alerts", Alerts.as_view()),
    path("alerts/<int:id>/acknowledge", AlertAction.as_view(action="acknowledge")),
    path("alerts/<int:id>/resolve", AlertAction.as_view(action="resolve")),
    path("inbox", Conversations.as_view()),
    path("inbox/<int:id>", ConversationDetail.as_view()),
    path("inbox/<int:id>/reply", ConversationReply.as_view()),
    path("inbox/<int:id>/close", ConversationClose.as_view()),
]
