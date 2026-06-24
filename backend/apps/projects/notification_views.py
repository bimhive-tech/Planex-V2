"""In-app notification API: list the caller's notifications (newest first, with
an unread count) and mark them read."""
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification

# Cap the dropdown payload — older items aren't useful in a bell menu.
_RECENT_LIMIT = 30


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    project_id = serializers.UUIDField(source="project.id", default=None, read_only=True)
    actor_name = serializers.CharField(source="actor.full_name", default="", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "kind_display", "message", "project_id", "actor_name",
                  "is_read", "created_at"]


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user).select_related("actor", "project")
        unread = qs.filter(is_read=False).count()
        data = NotificationSerializer(qs[:_RECENT_LIMIT], many=True).data
        return Response({"results": data, "unread_count": unread})


class NotificationReadView(APIView):
    """Mark notifications read. With an `ids` list, marks those; otherwise all."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        qs = Notification.objects.filter(recipient=request.user, is_read=False)
        ids = request.data.get("ids")
        if ids:
            qs = qs.filter(id__in=ids)
        qs.update(is_read=True)
        return Response({"unread_count": Notification.objects.filter(recipient=request.user, is_read=False).count()})
