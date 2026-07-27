"""Admin registrations for the AI assistant app. AiFeatureRequest review lives
here for v1 — low enough volume that a bespoke UI isn't worth building yet."""
from django.contrib import admin

from .models import AiFeatureRequest, ChatSession


@admin.register(AiFeatureRequest)
class AiFeatureRequestAdmin(admin.ModelAdmin):
    list_display = ["summary", "company", "project", "status", "created_at"]
    list_filter = ["company", "status"]
    actions = ["mark_sent", "mark_dismissed"]

    @admin.action(description="Mark selected as sent to Planex support")
    def mark_sent(self, request, queryset):
        queryset.update(status=AiFeatureRequest.Status.SENT)

    @admin.action(description="Dismiss selected")
    def mark_dismissed(self, request, queryset):
        queryset.update(status=AiFeatureRequest.Status.DISMISSED)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "user", "updated_at"]
    list_filter = ["company"]
