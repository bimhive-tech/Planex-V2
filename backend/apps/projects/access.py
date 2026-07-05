"""Scope-based access: a member restricted to specific scopes only sees those.

Rule (mirrors Planex): no grants -> full access; one or more grants -> limited to
those scopes and everything under them. Platform admins and MANAGE_PROJECTS bypass.

Module access itself (which tabs/endpoints a user may use at all) is governed by
company role permissions (apps.accounts.constants.Permission) — the same system
used everywhere else in the app. Scope only narrows the DATA visible within a
module the user already has access to.
"""
from apps.accounts.constants import Permission

from .models import ProjectScopeAccess


def is_project_admin(user):
    """Platform admins and company MANAGE_PROJECTS holders see the whole project."""
    return user.is_platform_admin or Permission.MANAGE_PROJECTS.value in user.effective_permissions()


def accessible_zone_ids(project, user):
    """Return None for full access, or the set of zone scope ids the user is limited to."""
    if is_project_admin(user):
        return None
    grants = set(ProjectScopeAccess.objects.filter(project=project, user=user)
                 .values_list("scope_id", flat=True))
    return grants or None


def accessible_scope_ids(project, user):
    """None for full access, else the set of all scope ids the user may see
    (the granted zones plus their whole subtree)."""
    zones = accessible_zone_ids(project, user)
    if zones is None:
        return None
    by_parent = {}
    for sid, pid in project.scopes.values_list("id", "parent_id"):
        by_parent.setdefault(pid, []).append(sid)
    accessible, stack = set(), list(zones)
    while stack:
        sid = stack.pop()
        if sid in accessible:
            continue
        accessible.add(sid)
        stack.extend(by_parent.get(sid, []))
    return accessible
