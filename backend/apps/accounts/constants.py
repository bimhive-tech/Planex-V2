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
    MANAGE_USERS = "manage_users", "Manage users"
    MANAGE_ROLES = "manage_roles", "Manage roles"
    MANAGE_DEPARTMENTS = "manage_departments", "Manage departments"

    # Project domain (used by later modules; defined now so roles are stable).
    MANAGE_PROJECTS = "manage_projects", "Manage projects"
    VIEW_PROJECTS = "view_projects", "View projects"
    SUBMIT_PROGRESS = "submit_progress", "Submit progress"
    REVIEW_PROGRESS = "review_progress", "Review progress"
    APPROVE_PROGRESS = "approve_progress", "Approve progress"
    EXPORT_REPORTS = "export_reports", "Export reports"


# Convenience groupings.
ALL_PERMISSIONS = [p.value for p in Permission]
PLATFORM_PERMISSIONS = [Permission.MANAGE_COMPANIES.value, Permission.MANAGE_PLATFORM.value]


class SeededRole:
    """Names of system-seeded roles. Created per company; not user-editable names."""

    PLATFORM_ADMIN = "Platform Admin"
    COMPANY_ADMIN = "Company Admin"


# Company admins can do everything inside their own company, but no platform ops.
COMPANY_ADMIN_PERMISSIONS = [
    p for p in ALL_PERMISSIONS if p not in PLATFORM_PERMISSIONS
]
