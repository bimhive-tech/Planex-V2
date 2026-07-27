"""The agent loop: calls OpenAI with the tool catalog + running history,
executes read tools immediately, stages write tools as proposals, and streams
text deltas out as they arrive. Runs synchronously in the request cycle (held
open via streaming) — matches how the rest of this backend already handles
even heavy work (see apps/projects/imports.py), no new job infrastructure."""
import json
import logging

from .models import ChatMessage
from .openai_client import AiNotConfigured, get_client, get_model
from .tools import ALL_TOOLS, PROPOSE_TOOLS, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = (
    "You are Planex's in-app assistant, for construction project management data only. "
    "You can only discuss this company's projects in Planex, and Planex's own features. "
    "If asked about anything else (general knowledge, other software, personal topics, "
    "coding, anything unrelated to this company's construction projects), politely decline "
    "and redirect to what you can help with. Never invent numbers — always call a tool to "
    "get real data; never guess a project's progress or figures from memory.\n\n"
    "You can read project data and give insights freely. Creating or editing a project, or "
    "importing a schedule from an uploaded file, always goes through a `propose_*` tool — "
    "these do NOT write anything by themselves, they show the user a confirmation card. Tell "
    "the user what you're proposing in plain language after calling one.\n\n"
    "When the user attaches a file, its extracted contents appear in their message. Read it "
    "yourself and decide how it maps onto Planex's Stage/Zone/Area/Phase/Activity model — "
    "there is no fixed column mapping, you classify each row based on what it actually "
    "contains (headings vs. line items, indentation, columns present). If something in the "
    "file doesn't fit any existing Planex category, do not silently drop it: mention it to the "
    "user and ask whether to flag it as a feature request for Planex support. Only call "
    "flag_unsupported_category after they say yes."
)


def _tool_result_content(name, kwargs, user):
    try:
        result = ALL_TOOLS[name](user, **kwargs)
    except Exception as exc:  # noqa: BLE001 — surfaced to the model, not a 500
        result = {"error": str(exc)}
    return result


def _user_content(m):
    """Attached files' extracted text rides along with the user's own message —
    the model reads it as part of the same turn, no separate tool call needed."""
    parts = [m.content] if m.content else []
    for att in m.attachments.all():
        parts.append(f"--- Attached file: {att.original_filename} ---\n{att.extracted_text}")
    return "\n\n".join(parts)


def _compact_tool_content(m):
    """A propose_* tool's result can carry an entire schedule tree — the model
    already generated that tree itself (it's sitting in its own preceding
    tool_calls arguments, which still gets replayed in full every round), so
    echoing the whole thing back a second time as the tool's result just
    doubles an already-large payload and compounds on every later round in
    the same conversation. The full result still gets persisted as-is (the
    confirm endpoint needs it) — this only affects what's replayed to the
    model on subsequent calls."""
    if m.tool_name not in PROPOSE_TOOLS:
        return m.content
    try:
        data = json.loads(m.content)
    except json.JSONDecodeError:
        return m.content
    compact = {k: v for k, v in data.items() if k not in ("tree", "fields", "unmapped")}
    return json.dumps(compact)


def _to_openai_messages(session):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in session.messages.order_by("created_at"):
        if m.role == ChatMessage.Role.ASSISTANT and m.tool_calls:
            messages.append({
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": m.tool_calls,
            })
        elif m.role == ChatMessage.Role.TOOL:
            messages.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": _compact_tool_content(m)})
        elif m.role == ChatMessage.Role.USER:
            messages.append({"role": "user", "content": _user_content(m)})
        else:
            messages.append({"role": m.role, "content": m.content})
    return messages


def stream_agent_reply(session, user):
    """Generator of SSE-framed JSON strings: {"type": "delta"|"proposal"|"done"|"error", ...}."""
    def sse(payload):
        return f"data: {json.dumps(payload)}\n\n"

    try:
        client = get_client()
        model = session.model or get_model()
    except AiNotConfigured as exc:
        yield sse({"type": "error", "message": str(exc)})
        return

    for _ in range(MAX_TOOL_ROUNDS):
        messages = _to_openai_messages(session)
        text_parts = []
        tool_calls_acc = {}  # index -> {"id":..., "name":..., "arguments": "..."}
        finish_reason = None

        try:
            # The gpt-5.6 family (our whole AVAILABLE_MODELS catalog) rejects
            # function tools on Chat Completions unless reasoning is turned
            # off this way — confirmed against the real API: "Function tools
            # with reasoning_effort are not supported... set reasoning_effort
            # to 'none'." (the alternative, the newer Responses API, would be
            # a bigger migration than this fix warrants right now).
            stream = client.chat.completions.create(
                model=model, messages=messages, tools=TOOL_SCHEMAS, stream=True,
                reasoning_effort="none",
            )
            for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    yield sse({"type": "delta", "content": delta.content})
                for tc in (delta.tool_calls or []):
                    acc = tool_calls_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.function and tc.function.name:
                        acc["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        acc["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except Exception as exc:  # noqa: BLE001 — network/API errors surfaced, not a crash
            logger.exception("AI agent loop failed for session %s", session.id)
            yield sse({"type": "error", "message": str(exc)})
            return

        full_text = "".join(text_parts)

        if finish_reason != "tool_calls" or not tool_calls_acc:
            ChatMessage.objects.create(
                session=session, role=ChatMessage.Role.ASSISTANT, content=full_text,
            )
            yield sse({"type": "done"})
            return

        ordered_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.ASSISTANT, content=full_text,
            tool_calls=[
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in ordered_calls
            ],
        )

        for call in ordered_calls:
            try:
                kwargs = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                kwargs = {}
            result = _tool_result_content(call["name"], kwargs, user)
            tool_msg = ChatMessage.objects.create(
                session=session, role=ChatMessage.Role.TOOL, content=json.dumps(result),
                tool_call_id=call["id"], tool_name=call["name"],
            )
            if call["name"] in PROPOSE_TOOLS and result.get("valid"):
                yield sse({"type": "proposal", "message_id": str(tool_msg.id), "proposal": result})

    yield sse({"type": "error", "message": "Stopped after too many tool-call rounds."})
