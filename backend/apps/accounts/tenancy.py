"""Tenant-scoping helpers. Every settings endpoint resolves the company a request
acts on through here, so isolation is enforced in one place.

Rule: a normal user is always locked to their own company. A platform-admin-company
user may target another company by passing its id (used by the company selector
in the Users/Roles tabs); otherwise they default to their own company.
"""
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import Company


def resolve_company(request, company_id=None) -> Company:
    """Return the Company this request should operate on, enforcing isolation."""
    user = request.user
    if company_id and user.is_platform_admin:
        try:
            return Company.objects.get(pk=company_id)
        except (Company.DoesNotExist, ValueError, TypeError):
            raise NotFound("Company not found.")
    if user.company is None:
        # Should not happen for seeded users; guard anyway.
        raise PermissionDenied("No company context for this user.")
    return user.company
