"""Business logic for the Settings module. Views/viewsets delegate here.

Tenant rule: callers pass an already-resolved `company` (see tenancy.resolve_company),
so every write is explicitly scoped to one company.
"""
from django.db import transaction

from .constants import (
    COMPANY_ADMIN_PERMISSIONS,
    DEFAULT_USER_PERMISSIONS,
    SeededRole,
    allowed_permissions,
)
from .models import Company, Membership, Role, User


def seed_default_roles(company: Company) -> None:
    """Create the two default roles every tenant company gets:
    - Company Admin: all company permissions, fully locked (no edit/delete).
    - User: minimal permissions, editable but not deletable.
    """
    Role.objects.get_or_create(
        company=company, name=SeededRole.COMPANY_ADMIN,
        defaults={"permissions": COMPANY_ADMIN_PERMISSIONS, "is_system": True, "is_locked": True},
    )
    Role.objects.get_or_create(
        company=company, name=SeededRole.USER,
        defaults={"permissions": DEFAULT_USER_PERMISSIONS, "is_system": True, "is_locked": False},
    )


@transaction.atomic
def create_company(*, name: str) -> Company:
    """Create a shell company + its default roles (no users yet)."""
    company = Company.objects.create(name=name)
    seed_default_roles(company)
    return company


@transaction.atomic
def delete_company(*, company: Company) -> None:
    """Irreversibly delete a company and everything it owns. Ordered to satisfy
    the PROTECT on Membership.role."""
    Membership.objects.filter(company=company).delete()
    User.objects.filter(company=company).delete()
    Role.objects.filter(company=company).delete()
    company.delete()


def _filter_permissions(company: Company, permissions: list[str]) -> list[str]:
    """Keep only permission keys this company is allowed to grant."""
    allowed = set(allowed_permissions(is_platform=company.is_platform_admin))
    # Preserve order, drop dupes + out-of-scope keys.
    seen, result = set(), []
    for key in permissions:
        if key in allowed and key not in seen:
            seen.add(key)
            result.append(key)
    return result


@transaction.atomic
def create_role(*, company: Company, name: str, permissions: list[str]) -> Role:
    return Role.objects.create(
        company=company,
        name=name.strip(),
        is_platform_role=False,
        permissions=_filter_permissions(company, permissions),
    )


@transaction.atomic
def update_role(*, role: Role, name: str | None = None, permissions: list[str] | None = None) -> Role:
    """Update a role's name (Roles tab) and/or permissions (Permissions matrix).
    Only the provided fields change. Locked-role enforcement happens in the view."""
    fields = []
    if name is not None:
        role.name = name.strip()
        fields.append("name")
    if permissions is not None:
        role.permissions = _filter_permissions(role.company, permissions)
        fields.append("permissions")
    if fields:
        role.save(update_fields=fields + ["updated_at"])
    return role


def _sync_memberships(*, user: User, company: Company, role_ids: list) -> None:
    """Replace a user's active memberships with exactly the given roles
    (validated to belong to the company)."""
    roles = list(Role.objects.filter(company=company, id__in=role_ids))
    user.memberships.all().delete()
    Membership.objects.bulk_create(
        Membership(company=company, user=user, role=role, is_active=True) for role in roles
    )


@transaction.atomic
def create_user(*, company: Company, email: str, password: str, first_name: str,
                last_name: str, phone_number: str, role_ids: list) -> User:
    user = User.objects.create_user(
        email=email,
        password=password,
        company=company,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
    )
    _sync_memberships(user=user, company=company, role_ids=role_ids)
    return user


@transaction.atomic
def update_user(*, user: User, data: dict) -> User:
    fields = []
    for field in ("first_name", "last_name", "phone_number", "is_active", "email"):
        if field in data:
            setattr(user, field, data[field].lower() if field == "email" else data[field])
            fields.append(field)
    if data.get("password"):
        user.set_password(data["password"])
        fields.append("password")
    if fields:
        user.save(update_fields=fields + ["updated_at"])
    if "role_ids" in data:
        _sync_memberships(user=user, company=user.company, role_ids=data["role_ids"])
    return user
