"""AI assistant chat sessions/messages, file attachments, and the flagged
"Planex doesn't support this yet" feature-request log."""
import uuid

from django.db import models

from apps.accounts.models import Company, TimestampedModel
from apps.projects.models import Project


class ChatSession(TimestampedModel):
    """One conversation with the assistant. Company-scoped (insights/actions
    span every project in the user's company), owned by the user who started it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="chat_sessions")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=200, blank=True)  # set from the first message
    # Blank = fall back to settings.OPENAI_MODEL. Picked per-conversation from
    # the model list in tools/constants.py (AVAILABLE_MODELS) so cost/quality
    # is a user choice, not a fixed deployment setting.
    model = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Chat {self.id}"


class ChatMessage(TimestampedModel):
    """One turn in a session. `tool_calls` holds the raw tool-call requests an
    assistant message made; `tool_call_id`/`tool_name` identify which call a
    role=tool message is the result of (OpenAI's own message-linking shape)."""

    class Role(models.TextChoices):
        SYSTEM = "system", "System"
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        TOOL = "tool", "Tool"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField(blank=True)
    tool_calls = models.JSONField(null=True, blank=True)
    tool_call_id = models.CharField(max_length=100, blank=True)
    tool_name = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["session", "created_at"])]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"


def chat_attachment_key(instance, filename):
    """Stable private storage key for a chat-uploaded file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"ai-attachments/{instance.message.session_id}/{uuid.uuid4()}.{ext}"


class ChatAttachment(TimestampedModel):
    """A file the user attached to a chat message. `extracted_text` is cached on
    upload so re-reading the conversation history never re-parses the file."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=chat_attachment_key)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True)

    def __str__(self):
        return self.original_filename


class AiFeatureRequest(TimestampedModel):
    """Something the assistant found in an imported file that Planex has no
    category for yet — raised only after the user agrees to send it. Reviewed
    via Django admin for now; no email, per the product call this mirrors."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent to Planex support"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="ai_feature_requests")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="ai_feature_requests")
    raised_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True,
                                   related_name="ai_feature_requests")
    summary = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.summary[:60]
