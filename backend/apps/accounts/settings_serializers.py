"""Serializers for the Settings module (company info, companies, users, roles).
One serializer per use case; validation here, business logic in services."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Company, Role, User


# ── Company info (own company) ────────────────────────────────────────────
class CompanyInfoSerializer(serializers.ModelSerializer):
    """Settings → Info tab. Editable profile fields; identity fields read-only."""

    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "is_platform_admin", "is_active",
            "phone_number", "email", "address", "website",
            "user_count", "created_at",
        ]
        read_only_fields = ["id", "slug", "is_platform_admin", "is_active", "created_at"]


# ── Companies (platform admin) ────────────────────────────────────────────
class CompanyListSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Company
        fields = ["id", "name", "slug", "is_active", "is_platform_admin", "user_count", "created_at"]


class CompanyCreateSerializer(serializers.Serializer):
    """Create-company is shell-only: a name. A default Company Admin role is
    seeded by the service so the company is immediately assignable."""

    name = serializers.CharField(max_length=200)

    def validate_name(self, value):
        value = value.strip()
        if Company.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A company with this name already exists.")
        return value


# ── Roles ─────────────────────────────────────────────────────────────────
class RoleSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = [
            "id", "name", "is_platform_role", "is_system", "is_locked",
            "permissions", "member_count", "created_at",
        ]
        read_only_fields = ["id", "is_platform_role", "is_system", "is_locked", "created_at"]


class RoleCreateSerializer(serializers.Serializer):
    """Create a custom role (name; permissions optional, set later in the matrix)."""

    name = serializers.CharField(max_length=120)
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=True, default=list)


class RoleUpdateSerializer(serializers.Serializer):
    """Partial update: name (Roles tab) and/or permissions (Permissions matrix).
    Keys are filtered to the company's allowed set in the service."""

    name = serializers.CharField(max_length=120, required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)


# ── Users ─────────────────────────────────────────────────────────────────
class UserListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    roles = serializers.SerializerMethodField()
    role_ids = serializers.SerializerMethodField()
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "phone_number", "is_active", "roles", "role_ids", "company_name", "created_at",
        ]

    def _active(self, obj):
        # memberships are prefetched in the viewset queryset.
        return [m for m in obj.memberships.all() if m.is_active]

    def get_roles(self, obj):
        return [m.role.name for m in self._active(obj)]

    def get_role_ids(self, obj):
        return [str(m.role_id) for m in self._active(obj)]


class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    phone_number = serializers.CharField(max_length=40, allow_blank=True, default="")
    role_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True, default=list)

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class UserUpdateSerializer(serializers.Serializer):
    """Edit a user — everything, including email and (optionally) password.
    Pass the target user via context['instance'] for the email-uniqueness check."""

    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                     trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    phone_number = serializers.CharField(max_length=40, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)
    # When omitted, memberships are left unchanged; when present, they're replaced.
    role_ids = serializers.ListField(child=serializers.UUIDField(), required=False)

    def validate_email(self, value):
        value = value.lower().strip()
        instance = self.context.get("instance")
        qs = User.objects.filter(email=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        if not value:
            return value  # blank = leave unchanged
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value
