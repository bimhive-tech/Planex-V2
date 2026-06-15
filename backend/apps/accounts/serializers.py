"""Serializers for the auth endpoints. One serializer per use case."""
from rest_framework import serializers

from .models import Company, User


class LoginSerializer(serializers.Serializer):
    """Validates login credentials (email + password)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


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
