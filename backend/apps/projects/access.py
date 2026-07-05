"""Scope-based access: a member restricted to specific zones only sees those.

Rule (mirrors Planex): no grants -> full access; one or more grants -> limited to
those zones and everything under them. Platform admins and MANAGE_PROJECTS bypass.
"""
from apps.accounts.constants import Permission

from .models import ProjectScopeAccess
from .permissions_catalog import ALL_PROJECT_PERMISSIONS


def is_project_admin(user):
    """Platform admins and company MANAGE_PROJECTS holders bypass project perms."""
    return user.is_platform_admin or Permission.MANAGE_PROJECTS.value in user.effective_permissions()


def project_permissions(project, user):
    """The set of per-project module permission keys this user holds on `project`.

    Admins implicitly hold all of them; otherwise it's the member's stored set
    (empty if they aren't a member of this project)."""
    if is_project_admin(user):
        return set(ALL_PROJECT_PERMISSIONS)
    member = project.members.filter(user=user).only("permissions", "project", "user").first()
    return set(member.permissions or []) if member else set()


def has_project_permission(project, user, perm):
    return perm in project_permissions(project, user)


def accessible_zone_ids(project, user):
    """Return None for full access, or the set of zone scope ids the user is limited to."""
    if user.is_platform_admin or Permission.MANAGE_PROJECTS.value in user.effective_permissions():
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
