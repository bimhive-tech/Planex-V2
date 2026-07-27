"""Commits an AI-proposed schedule tree into Planex's real Stage/Zone/Area/
Phase/Activity hierarchy. Unlike the deterministic P6/zone-tracker parsers
(which derive structure from fixed column positions or WBS indentation), the
model itself decides each node's `scope_type` and where activities/milestones
belong — this just trusts that classification and writes it, the same way
`build_from_p6_schedule` writes an already-parsed tree. Full replace only
(matches the deterministic importers), per the product decision for v1."""
from decimal import Decimal, InvalidOperation

from apps.accounts.constants import Permission
from apps.projects.models import Activity, Milestone, Project, ProjectScope

VALID_SCOPE_TYPES = {c[0] for c in ProjectScope.ScopeType.choices}


def _dec(value, default=None):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def summarize_tree(tree: list[dict]) -> dict:
    """Counts for the confirmation card — no DB writes."""
    counts = {"scopes": 0, "activities": 0, "milestones": 0}

    def walk(nodes):
        for node in nodes:
            if node.get("is_milestone"):
                counts["milestones"] += 1
                continue
            counts["scopes"] += 1
            for _ in node.get("activities", []):
                counts["activities"] += 1
            walk(node.get("children", []))

    walk(tree)
    return counts


def commit_tree(project: Project, tree: list[dict], *, replace: bool = True) -> dict:
    """Writes the proposed tree for real. Raises ValueError on a node with an
    unrecognized scope_type rather than silently guessing one."""
    company = project.company
    if replace:
        project.scopes.all().delete()

    counts = {"scopes": 0, "activities": 0, "milestones": 0}

    def make_scope(node, parent, order):
        scope_type = node.get("scope_type")
        if scope_type not in VALID_SCOPE_TYPES:
            raise ValueError(f"Unrecognized scope_type {scope_type!r} for node {node.get('name')!r}")
        scope = ProjectScope.objects.create(
            company=company, project=project, parent=parent, scope_type=scope_type,
            name=(node.get("name") or "Untitled")[:180], sort_order=order,
            planned_start=node.get("start") or None, planned_finish=node.get("finish") or None,
        )
        counts["scopes"] += 1
        for i, act in enumerate(node.get("activities", [])):
            Activity.objects.create(
                company=company, project=project, scope=scope,
                name=(act.get("name") or "Untitled")[:200], sort_order=i,
                weight=_dec(act.get("weight"), Decimal("1")) or Decimal("1"),
                progress_percent=_dec(act.get("progress_percent"), Decimal("0")) or Decimal("0"),
                planned_start=act.get("start") or None, planned_finish=act.get("finish") or None,
            )
            counts["activities"] += 1
        for i, child in enumerate(node.get("children", [])):
            make_scope(child, scope, i)

    def make_milestone(node, order):
        Milestone.objects.create(
            company=company, project=project, title=(node.get("name") or "Untitled")[:180],
            date=node.get("start") or node.get("finish") or None, sort_order=order,
        )
        counts["milestones"] += 1

    for i, node in enumerate(tree):
        if node.get("is_milestone"):
            make_milestone(node, i)
        else:
            make_scope(node, None, i)

    return counts


def require_ai_import_permission(user, project: Project):
    """Same permission a human import already needs — the assistant acts as
    the calling user, never with elevated access."""
    from rest_framework.exceptions import PermissionDenied

    if Permission.MANAGE_PROJECTS.value not in user.effective_permissions():
        raise PermissionDenied("You don't have permission to import into projects.")
    if project.company_id != user.company_id:
        raise PermissionDenied("Project not found.")
