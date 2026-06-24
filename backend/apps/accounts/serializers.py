"""Serializers for the auth endpoints. One serializer per use case."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Company, User


class LoginSerializer(serializers.Serializer):
    """Validates login credentials (email + password)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    """Self-service password change: confirm the current password, set a new one."""

    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        try:
            validate_password(value, self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class CompanyBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "slug", "is_platform_admin"]


class CurrentUserSerializer(serializers.ModelSerializer):
    """Profile of the signed-in user, including resolved permissions + roles."""

    full_name = serializers.CharField(read_only=True)
    company = CompanyBriefSerializer(read_only=True)
    is_platform_admin = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "company",
            "is_platform_admin",
            "permissions",
            "roles",
        ]

    def get_permissions(self, obj):
        return sorted(obj.effective_permissions())

    def get_roles(self, obj):
        return [m.role.name for m in obj.memberships.filter(is_active=True).select_related("role")]
