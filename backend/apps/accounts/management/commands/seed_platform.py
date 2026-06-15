"""Seed the administrative company + SuperAdmin user. Idempotent.

Creates (if missing):
  - Company "Admin" with is_platform_admin=True
  - Role "Platform Admin" (all platform + company permissions)
  - User superadmin@planex.app / 12345678 (overridable via env)
  - Membership linking the user to the role

Run: python manage.py seed_platform
Credentials come from env (SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD) with sane
defaults, so secrets aren't hardcoded for real deployments.
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.constants import ALL_PERMISSIONS, SeededRole
from apps.accounts.models import Company, Membership, Role, User

PLATFORM_COMPANY_NAME = "Admin"


class Command(BaseCommand):
    help = "Seed the platform-admin company and SuperAdmin user (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        email = os.environ.get("SUPERADMIN_EMAIL", "superadmin@planex.app").lower()
        password = os.environ.get("SUPERADMIN_PASSWORD", "12345678")

        company, created_company = Company.objects.get_or_create(
            name=PLATFORM_COMPANY_NAME,
            defaults={"is_platform_admin": True, "is_active": True},
        )
        if not company.is_platform_admin:
            company.is_platform_admin = True
            company.save(update_fields=["is_platform_admin"])

        role, _ = Role.objects.get_or_create(
            company=company,
            name=SeededRole.PLATFORM_ADMIN,
            defaults={"is_platform_role": True, "permissions": ALL_PERMISSIONS,
                      "is_system": True, "is_locked": True},
        )
        # Keep the seeded role current with the code (perms + system/locked flags).
        if (set(role.permissions or []) != set(ALL_PERMISSIONS)
                or not role.is_system or not role.is_locked):
            role.permissions = ALL_PERMISSIONS
            role.is_platform_role = True
            role.is_system = True
            role.is_locked = True
            role.save(update_fields=["permissions", "is_platform_role", "is_system", "is_locked"])

        user, created_user = User.objects.get_or_create(
            email=email,
            defaults={
                "company": company,
                "first_name": "Super",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created_user:
            user.set_password(password)
            user.save()
        else:
            # Ensure linkage stays correct without clobbering a changed password.
            changed = False
            if user.company_id != company.id:
                user.company = company
                changed = True
            if not (user.is_staff and user.is_superuser):
                user.is_staff = user.is_superuser = True
                changed = True
            if changed:
                user.save()

        Membership.objects.get_or_create(
            company=company, user=user, role=role, department=None,
            defaults={"is_active": True},
        )

        self.stdout.write(self.style.SUCCESS(
            f"Platform seeded. Company={company.name} "
            f"User={user.email} ({'created' if created_user else 'existing'})"
        ))
