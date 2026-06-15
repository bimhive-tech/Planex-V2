"""Reusable DRF permission classes built on action-permission keys."""
from rest_framework.permissions import BasePermission


class HasPermission(BasePermission):
    """Grants access when the user holds a required permission key.

    Usage: set `required_permission` on the view, or subclass with it set.
    Platform-admin company users implicitly pass (handled in effective_permissions).
    """

    def has_permission(self, request, view):
        required = getattr(view, "required_permission", None)
        if required is None:
            return True
        user = request.user
        return bool(user and user.is_authenticated and required in user.effective_permissions())


class IsPlatformAdmin(BasePermission):
    """Only users in the administrative (platform-admin) company."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_platform_admin)
