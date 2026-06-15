"""Django admin registrations for the accounts app (internal tooling only)."""
from django.contrib import admin

from .models import Company, Department, Membership, Role, User


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_platform_admin", "is_active", "created_at")
    search_fields = ("name", "slug")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "company", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    list_filter = ("is_active", "is_staff", "company")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_platform_role")
    list_filter = ("company", "is_platform_role")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "company")
    list_filter = ("company",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "company", "is_active")
    list_filter = ("company", "is_active")
