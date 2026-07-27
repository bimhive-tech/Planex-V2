"""AI assistant routes, mounted under /api/."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    ChatMessageListView,
    ChatMessageStreamView,
    ChatProposalConfirmView,
    ChatSessionViewSet,
)

router = SimpleRouter(trailing_slash=True)
router.register("ai/sessions", ChatSessionViewSet, basename="ai-sessions")

urlpatterns = [
    path("ai/sessions/<uuid:session_id>/messages/", ChatMessageListView.as_view(), name="ai-messages"),
    path("ai/sessions/<uuid:session_id>/messages/send/", ChatMessageStreamView.as_view(), name="ai-messages-send"),
    path("ai/sessions/<uuid:session_id>/messages/<uuid:message_id>/confirm/",
         ChatProposalConfirmView.as_view(), name="ai-proposal-confirm"),
    *router.urls,
]
