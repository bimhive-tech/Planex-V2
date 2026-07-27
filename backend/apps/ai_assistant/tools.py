"""The assistant's tool catalog. Every tool is a thin, permission-scoped
wrapper around existing service functions — the model never gets raw DB
access, and every call runs with the *calling user's own* permissions, never
elevated ones. Read tools execute immediately; write tools (name starts with
`propose_`) only validate and describe what *would* happen — the actual
write happens later, from a plain confirm click in the UI, via
`commit_proposal` (never re-invoking the model)."""
from decimal import Decimal

from django.db.models import Sum
from rest_framework.exceptions import PermissionDenied

from apps.accounts.constants import Permission
from apps.projects.models import Project
from apps.projects.serializers import ProjectWriteSerializer
from apps.projects.services import project_overall_progress
from apps.reports.services import _breakdown, _duration, _planned_progress

from .generic_schedule_import import build_tree_from_rule
from .generic_schedule_import import summarize_tree as summarize_rule_tree
from .generic_schedule_import import tree_from_json_safe, tree_to_json_safe
from .import_tree import commit_tree, require_ai_import_permission, summarize_tree
from .models import AiFeatureRequest, ChatAttachment


def _project_or_404(user, project_id):
    try:
        return Project.objects.get(pk=project_id, company=user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise PermissionDenied("Project not found.")


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


# ── Read tools (auto-execute) ───────────────────────────────────────────────

def list_projects(user, **_):
    """Every project in the caller's company with its current overall progress."""
    if Permission.VIEW_PROJECTS.value not in user.effective_permissions():
        raise PermissionDenied("You don't have permission to view projects.")
    rows = []
    for p in Project.objects.filter(company=user.company, is_archived=False).order_by("name"):
        rows.append({
            "id": str(p.id), "name": p.name, "project_type": p.project_type,
            "overall_progress": project_overall_progress(p),
            "planned_start": _json_safe(p.planned_start), "planned_finish": _json_safe(p.planned_finish),
        })
    return {"projects": rows}


def get_project_insights(user, project_id, **_):
    """Progress (actual + planned), breakdown, duration/delay, milestones, and a
    light finance summary — reusing the exact figures the reports tab shows,
    not a re-derived approximation."""
    if Permission.VIEW_PROJECTS.value not in user.effective_permissions():
        raise PermissionDenied("You don't have permission to view projects.")
    project = _project_or_404(user, project_id)
    import datetime
    today = datetime.date.today()

    breakdown = _breakdown(project)
    duration = _duration(project, today)
    milestones = list(
        project.milestones.order_by("sort_order", "date").values("title", "date", "status")[:20]
    )
    cashflow_totals = project.cashflow_entries.aggregate(planned=Sum("planned"), actual=Sum("actual"))
    invoices_total = project.invoices.aggregate(total=Sum("value"))["total"]

    return {
        "id": str(project.id), "name": project.name,
        "overall_progress": project_overall_progress(project),
        "planned_progress": _planned_progress(project, today, use_imported=True),
        "breakdown": breakdown,
        "duration": duration,
        "milestones": [
            {"title": m["title"], "date": _json_safe(m["date"]), "status": m["status"]}
            for m in milestones
        ],
        "cashflow_planned_total": _json_safe(cashflow_totals["planned"]) if cashflow_totals["planned"] else 0,
        "cashflow_actual_total": _json_safe(cashflow_totals["actual"]) if cashflow_totals["actual"] else 0,
        "invoices_total": _json_safe(invoices_total) if invoices_total else 0,
    }


def flag_unsupported_category(user, summary, project_id=None, **_):
    """Logs a "Planex can't place this yet" note for platform review. Only call
    this after the user has explicitly agreed, in the conversation, to send it —
    never on the model's own initiative."""
    project = _project_or_404(user, project_id) if project_id else None
    req = AiFeatureRequest.objects.create(
        company=user.company, project=project, raised_by=user,
        summary=summary, status=AiFeatureRequest.Status.PENDING,
    )
    return {"id": str(req.id), "status": req.status}


# ── Propose tools (validate + describe only — no DB writes) ────────────────

def propose_create_project(user, **fields):
    if Permission.MANAGE_PROJECTS.value not in user.effective_permissions():
        raise PermissionDenied("You don't have permission to create projects.")
    serializer = ProjectWriteSerializer(data=fields, context={"company": user.company})
    if not serializer.is_valid():
        return {"valid": False, "errors": serializer.errors}
    return {
        "valid": True,
        "action": "create_project",
        "fields": {k: _json_safe(v) for k, v in serializer.validated_data.items()},
        "summary": f"Create project \"{fields.get('name')}\"",
    }


def propose_import_tree(user, project_id, tree, unmapped=None, **_):
    """`tree` is the model's own classified Stage/Zone/Area/Phase/Activity
    structure (see the system prompt for the exact shape) — this only
    sanity-checks and counts it, it does not decide placement itself."""
    project = _project_or_404(user, project_id)
    require_ai_import_permission(user, project)
    if not isinstance(tree, list) or not tree:
        return {"valid": False, "errors": "tree must be a non-empty list of nodes."}
    try:
        counts = summarize_tree(tree)
    except Exception as exc:  # noqa: BLE001 — surfaced to the model as a validation error, not a crash
        return {"valid": False, "errors": str(exc)}
    return {
        "valid": True,
        "action": "import_tree",
        "project_id": str(project.id),
        "tree": tree,
        "unmapped": unmapped or [],
        "counts": counts,
        "summary": (
            f"Import {counts['scopes']} scopes, {counts['activities']} activities, "
            f"{counts['milestones']} milestones into \"{project.name}\" "
            f"(replacing its current schedule)"
        ),
    }


def propose_import_via_rule(user, project_id, attachment_id, rule, **_):
    """For large tabular files: instead of the model re-emitting every row as
    a classified tree (bounded by the model's own output-token limit, not
    Planex's), it describes the file's column layout + hierarchy pattern
    once, and this applies that rule to every row in ordinary Python code —
    scales to files of any size, and produces exact, complete results the
    same way the deterministic P6 importer already does, because it feeds
    the SAME downstream pipeline (build_from_p6_schedule)."""
    project = _project_or_404(user, project_id)
    require_ai_import_permission(user, project)
    try:
        attachment = ChatAttachment.objects.get(
            pk=attachment_id, message__session__company=user.company, message__session__user=user,
        )
    except (ChatAttachment.DoesNotExist, ValueError, TypeError):
        return {"valid": False, "errors": "Attachment not found."}

    import openpyxl

    try:
        wb = openpyxl.load_workbook(attachment.file, data_only=True, read_only=True)
        try:
            roots = build_tree_from_rule(wb, rule)
        finally:
            wb.close()
    except Exception as exc:  # noqa: BLE001 — surfaced to the model as a validation error, not a crash
        return {"valid": False, "errors": f"Couldn't apply that rule to the file: {exc}"}

    if not roots:
        return {"valid": False, "errors": "No rows matched that rule — double-check the column indices."}

    counts = summarize_rule_tree(roots)
    return {
        "valid": True,
        "action": "import_via_rule",
        "project_id": str(project.id),
        "tree_json": tree_to_json_safe(roots),
        "counts": counts,
        "summary": (
            f"Import {counts['scopes']} scopes, {counts['activities']} activities, "
            f"{counts['milestones']} milestones into \"{project.name}\" "
            f"(replacing its current schedule), weighted by {counts['weighted_by']}"
        ),
    }


# ── Commit — invoked by the confirm endpoint directly, never by the model ──

def commit_proposal(user, proposal: dict):
    action = proposal.get("action")
    if action == "create_project":
        if Permission.MANAGE_PROJECTS.value not in user.effective_permissions():
            raise PermissionDenied("You don't have permission to create projects.")
        serializer = ProjectWriteSerializer(data=proposal["fields"], context={"company": user.company})
        serializer.is_valid(raise_exception=True)
        project = serializer.save(company=user.company)
        return {"id": str(project.id), "name": project.name}
    if action == "import_tree":
        project = _project_or_404(user, proposal["project_id"])
        require_ai_import_permission(user, project)
        return commit_tree(project, proposal["tree"], replace=True)
    if action == "import_via_rule":
        from apps.projects.p6_schedule_import import build_from_p6_schedule

        project = _project_or_404(user, proposal["project_id"])
        require_ai_import_permission(user, project)
        roots = tree_from_json_safe(proposal["tree_json"])
        return build_from_p6_schedule(project, roots, replace=True, source="ai-import")
    raise ValueError(f"Unknown proposal action: {action!r}")


READ_TOOLS = {
    "list_projects": list_projects,
    "get_project_insights": get_project_insights,
    "flag_unsupported_category": flag_unsupported_category,
}
PROPOSE_TOOLS = {
    "propose_create_project": propose_create_project,
    "propose_import_tree": propose_import_tree,
    "propose_import_via_rule": propose_import_via_rule,
}
ALL_TOOLS = {**READ_TOOLS, **PROPOSE_TOOLS}


# ── OpenAI function-calling schemas ─────────────────────────────────────────
# A tree node: {name, scope_type: stage|zone|area|phase|building|task,
# start?, finish?, is_milestone?, activities: [{name, progress_percent, weight,
# start?, finish?}], children: [node, ...]}. Leave activities only on nodes
# that hold actual work (mirrors how Planex's own hierarchy works); everything
# else is a grouping node with children.
_TREE_NODE_DESC = (
    "A node: {name, scope_type (one of stage/zone/area/phase/building/task), "
    "start (YYYY-MM-DD, optional), finish (optional), is_milestone (bool, optional — "
    "a milestone has no cost/duration/children, just a date), "
    "activities: [{name, progress_percent (0-100), weight (relative size, e.g. cost or "
    "quantity — use 1 if the file gives no sensible weight), start, finish}], "
    "children: [nested nodes, same shape]}."
)

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "list_projects",
        "description": "List every project in the user's company with its current overall progress.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_project_insights",
        "description": "Get a project's progress (actual + planned), completion breakdown, "
                        "duration/delay, milestones, and finance totals.",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "UUID of the project."}},
            "required": ["project_id"],
        },
    }},
    {"type": "function", "function": {
        "name": "flag_unsupported_category",
        "description": "Log a note that an imported file had data Planex has no place for yet. "
                        "Only call this after the user explicitly agreed, in this conversation, "
                        "to send it — never on your own initiative.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What the data was and why it didn't fit."},
                "project_id": {"type": "string", "description": "UUID of the related project, if any."},
            },
            "required": ["summary"],
        },
    }},
    {"type": "function", "function": {
        "name": "propose_create_project",
        "description": "Propose creating a new project. This does NOT create it yet — the user "
                        "must confirm the proposal in the UI first.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "project_type": {"type": "string", "enum": ["commercial", "residential", "infrastructure", "industrial"]},
                "location": {"type": "string"},
                "description": {"type": "string"},
                "planned_start": {"type": "string", "description": "YYYY-MM-DD"},
                "planned_finish": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["name", "project_type"],
        },
    }},
    {"type": "function", "function": {
        "name": "propose_import_tree",
        "description": "Propose importing a classified Stage/Zone/Area/Phase schedule tree you built "
                        "yourself, node by node, from an uploaded file's contents into a project. Only "
                        "use this for SMALL files (roughly under 50 rows) or ones with irregular "
                        "structure that propose_import_via_rule's column-mapping approach can't "
                        "describe. For a large regular table, use propose_import_via_rule instead — "
                        "building this tree by hand for hundreds of rows will hit your own output "
                        "limit and produce an incomplete result. This does NOT write anything yet — "
                        "the user must confirm in the UI first, and it replaces the project's current "
                        "schedule. Use `unmapped` for anything in the file you couldn't place in "
                        "Planex's model (a category it doesn't support yet).",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "tree": {"type": "array", "items": {"type": "object"}, "description": _TREE_NODE_DESC},
                "unmapped": {"type": "array", "items": {"type": "string"},
                             "description": "Short descriptions of data you couldn't place anywhere."},
            },
            "required": ["project_id", "tree"],
        },
    }},
    {"type": "function", "function": {
        "name": "propose_import_via_rule",
        "description": (
            "Propose importing a LARGE tabular schedule file by describing its column layout and "
            "hierarchy pattern ONCE, instead of re-typing every row yourself — Planex applies your "
            "rule to every row in code, so it handles files of any size correctly and completely. "
            "Use this whenever the file has a regular table where one column's text is indented with "
            "leading spaces to show WBS/hierarchy depth (a heading row), and a separate column is "
            "filled in ONLY on real leaf activity rows (blank on headings) — this is the common shape "
            "for P6-style and MS-Project-style schedule exports. Prefer this over propose_import_tree "
            "for anything more than ~50 rows. This does NOT write anything yet — the user must confirm "
            "in the UI first, and it replaces the project's current schedule."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "attachment_id": {"type": "string", "description": "The attachment_id shown with the file in the conversation."},
                "rule": {
                    "type": "object",
                    "description": "Describes the file's shape once; applied to every row in code.",
                    "properties": {
                        "sheet_name": {"type": "string", "description": "Sheet to read, if there's more than one."},
                        "header_row_index": {"type": "integer", "description": "0-based row index of the column header row."},
                        "columns": {
                            "type": "object",
                            "properties": {
                                "hierarchy_text": {"type": "integer", "description": "0-based column index whose text's leading spaces encode WBS depth — also the code/ID text on leaf rows."},
                                "name": {"type": "integer", "description": "0-based column index with the activity's own name/description — blank on heading rows, filled only on leaf activity rows."},
                                "start": {"type": "integer", "description": "0-based column index of the start date, if present."},
                                "finish": {"type": "integer", "description": "0-based column index of the finish date, if present."},
                                "progress_percent": {"type": "integer", "description": "0-based column index of a 0-100 or 0-1 percent-complete value, if present."},
                                "weight": {"type": "integer", "description": "0-based column index of whatever should drive roll-up weighting (cost, quantity, or duration), if present."},
                            },
                            "required": ["hierarchy_text", "name"],
                        },
                    },
                    "required": ["columns"],
                },
            },
            "required": ["project_id", "attachment_id", "rule"],
        },
    }},
]
