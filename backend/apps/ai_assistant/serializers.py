"""Serializers for the AI assistant's session/message history endpoints."""
from rest_framework import serializers

from .constants import AVAILABLE_MODEL_IDS
from .models import ChatAttachment, ChatMessage, ChatSession


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "title", "model", "created_at", "updated_at"]

    def validate_model(self, value):
        if value and value not in AVAILABLE_MODEL_IDS:
            raise serializers.ValidationError("Unknown model.")
        return value


class ChatAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatAttachment
        fields = ["id", "original_filename", "content_type", "size_bytes"]


class ChatMessageSerializer(serializers.ModelSerializer):
    attachments = ChatAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "tool_name", "created_at", "attachments"]
