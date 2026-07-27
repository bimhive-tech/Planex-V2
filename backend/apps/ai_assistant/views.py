"""AI assistant API: sessions, message history, the streaming send-message
endpoint, and confirming a pending proposal. Thin views — the agent loop and
tool execution live in services.py/tools.py."""
import json

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .constants import AVAILABLE_MODELS
from .extract import extract_text
from .models import ChatAttachment, ChatMessage, ChatSession
from .serializers import ChatMessageSerializer, ChatSessionSerializer
from .services import stream_agent_reply
from .tools import commit_proposal

MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024


class AiAssistantAccess(BasePermission):
    """Both gates must hold: the platform admin switched AI on for this
    company, and the user's role grants USE_AI_ASSISTANT."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.company):
            return False
        return bool(
            user.company.ai_enabled
            and Permission.USE_AI_ASSISTANT.value in user.effective_permissions()
        )


class ChatSessionViewSet(viewsets.ModelViewSet):
    """A user's own conversations — not shared across the company, even though
    the assistant's own data reach spans every project in it."""

    permission_classes = [IsAuthenticated, AiAssistantAccess]
    serializer_class = ChatSessionSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return ChatSession.objects.filter(company=self.request.user.company, user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, user=self.request.user)


class AiModelsView(APIView):
    """The models the chat's picker offers, with per-1M-token prices so the
    user can weigh cost against capability themselves."""

    permission_classes = [IsAuthenticated, AiAssistantAccess]

    def get(self, request):
        return Response(AVAILABLE_MODELS)


class ChatMessageListView(APIView):
    """GET the full history of one session, plus any confirmation still
    awaiting a decision — that's what lets a pending proposal's card survive
    a reload or a dropped connection instead of only existing for the
    instant it was first streamed."""

    permission_classes = [IsAuthenticated, AiAssistantAccess]

    def get(self, request, session_id):
        session = get_object_or_404(ChatSession, pk=session_id, company=request.user.company, user=request.user)
        messages = session.messages.exclude(role=ChatMessage.Role.SYSTEM).exclude(role=ChatMessage.Role.TOOL)
        pending = session.messages.filter(proposal_status=ChatMessage.ProposalStatus.PENDING)
        return Response({
            "results": ChatMessageSerializer(messages, many=True).data,
            "pending_proposals": [
                {"message_id": str(m.id), "proposal": json.loads(m.content)} for m in pending
            ],
        })


class ChatMessageStreamView(APIView):
    """POST a message (+ optional file). Streams the assistant's reply as
    Server-Sent Events — text deltas as they arrive, plus proposal/done/error
    events. Runs synchronously in the request cycle, held open by the stream."""

    permission_classes = [IsAuthenticated, AiAssistantAccess]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, session_id):
        session = get_object_or_404(ChatSession, pk=session_id, company=request.user.company, user=request.user)
        content = request.data.get("content", "").strip()
        upload = request.FILES.get("file")
        if not content and not upload:
            raise ValidationError("Message content or a file is required.")

        user_msg = ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=content)
        if upload:
            if upload.size > MAX_ATTACHMENT_BYTES:
                raise ValidationError(f"File must be {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB or smaller.")
            extracted = extract_text(upload, upload.name, upload.content_type or "")
            upload.seek(0)
            ChatAttachment.objects.create(
                message=user_msg, file=upload, original_filename=upload.name,
                content_type=upload.content_type or "", size_bytes=upload.size,
                extracted_text=extracted,
            )

        if not session.title:
            session.title = content[:80] or (upload.name if upload else "New chat")
            session.save(update_fields=["title", "updated_at"])
        else:
            session.save(update_fields=["updated_at"])  # bump ordering

        response = StreamingHttpResponse(
            stream_agent_reply(session, request.user), content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class ChatProposalConfirmView(APIView):
    """POST to commit (or cancel) a pending propose_* tool result."""

    permission_classes = [IsAuthenticated, AiAssistantAccess]

    def post(self, request, session_id, message_id):
        session = get_object_or_404(ChatSession, pk=session_id, company=request.user.company, user=request.user)
        tool_msg = get_object_or_404(ChatMessage, pk=message_id, session=session, role=ChatMessage.Role.TOOL)

        if tool_msg.proposal_status != ChatMessage.ProposalStatus.PENDING:
            raise ValidationError(f"This proposal was already {tool_msg.proposal_status or 'resolved'}.")

        if not request.data.get("confirm"):
            tool_msg.proposal_status = ChatMessage.ProposalStatus.CANCELLED
            tool_msg.save(update_fields=["proposal_status", "updated_at"])
            return Response({"cancelled": True})

        try:
            proposal = json.loads(tool_msg.content)
        except json.JSONDecodeError:
            raise ValidationError("This proposal can no longer be read.")
        if not proposal.get("valid"):
            raise ValidationError("This proposal is no longer valid.")

        try:
            result = commit_proposal(request.user, proposal)
        except PermissionDenied:
            raise
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not a 500
            raise ValidationError(str(exc))

        tool_msg.proposal_status = ChatMessage.ProposalStatus.CONFIRMED
        tool_msg.save(update_fields=["proposal_status", "updated_at"])
        return Response({"committed": True, "result": result})
