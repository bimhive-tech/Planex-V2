"""Single source of truth for permission keys and seeded role names.

Permission strings are defined ONCE here and reused everywhere (roles, checks,
frontend) — never re-typed as literals. New capabilities get a key here.
"""
from django.db import models


class Permission(models.TextChoices):
    """Action permissions — what a user is allowed to do (role-controlled)."""

    # Platform-level (only the administrative company's roles get these).
    MANAGE_COMPANIES = "manage_companies", "Manage companies"
    MANAGE_PLATFORM = "manage_platform", "Manage platform"

    # Company-level administration.
    MANAGE_COMPANY = "manage_company", "Manage company info"
    MANAGE_USERS = "manage_users", "Manage users"
    MANAGE_ROLES = "manage_roles", "Manage roles"
    MANAGE_DEPARTMENTS = "manage_departments", "Manage departments"

    # Project domain (used by later modules; defined now so roles are stable).
    MANAGE_PROJECTS = "manage_projects", "Manage projects"
    VIEW_PROJECTS = "view_projects", "View projects"
    SUBMIT_PROGRESS = "submit_progress", "Submit progress"
    REVIEW_PROGRESS = "review_progress", "Review progress"
    APPROVE_PROGRESS = "approve_progress", "Approve progress"
    DELETE_PROGRESS_IMAGES = "delete_progress_images", "Delete progress images"
    EXPORT_REPORTS = "export_reports", "Export reports"


# Convenience groupings.
ALL_PERMISSIONS = [p.value for p in Permission]
PLATFORM_PERMISSIONS = [Permission.MANAGE_COMPANIES.value, Permission.MANAGE_PLATFORM.value]


class SeededRole:
    """Names of system-seeded roles. Created per company; not user-editable names."""

    PLATFORM_ADMIN = "Platform Admin"
    COMPANY_ADMIN = "Company Admin"
    USER = "User"


# Company admins can do everything inside their own company, but no platform ops.
COMPANY_ADMIN_PERMISSIONS = [
    p for p in ALL_PERMISSIONS if p not in PLATFORM_PERMISSIONS
]

# Sensible minimal default for the seeded "User" role (editable later in the matrix).
DEFAULT_USER_PERMISSIONS = [Permission.VIEW_PROJECTS.value]


# Grouped catalog for the Roles UI (checkbox sections). Order matters for display.
PERMISSION_GROUPS = [
    ("Administration", [
        Permission.MANAGE_COMPANY.value,
        Permission.MANAGE_USERS.value,
        Permission.MANAGE_ROLES.value,
        Permission.MANAGE_DEPARTMENTS.value,
    ]),
    ("Projects", [
        Permission.MANAGE_PROJECTS.value,
        Permission.VIEW_PROJECTS.value,
        Permission.SUBMIT_PROGRESS.value,
        Permission.REVIEW_PROGRESS.value,
        Permission.APPROVE_PROGRESS.value,
        Permission.DELETE_PROGRESS_IMAGES.value,
        Permission.EXPORT_REPORTS.value,
    ]),
    ("Platform", PLATFORM_PERMISSIONS),
]

_LABELS = {p.value: p.label for p in Permission}


def allowed_permissions(*, is_platform: bool) -> list[str]:
    """Permission keys a company's roles may hold (platform keys only for the
    administrative company)."""
    return ALL_PERMISSIONS if is_platform else COMPANY_ADMIN_PERMISSIONS


def permission_catalog(*, is_platform: bool) -> list[dict]:
    """Grouped {group, key, label} list for building the Roles permission UI,
    filtered to what the given company is allowed to grant."""
    allowed = set(allowed_permissions(is_platform=is_platform))
    catalog = []
    for group, keys in PERMISSION_GROUPS:
        items = [{"key": k, "label": _LABELS[k]} for k in keys if k in allowed]
        if items:
            catalog.append({"group": group, "permissions": items})
    return catalog
