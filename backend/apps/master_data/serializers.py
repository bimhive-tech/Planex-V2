"""Serializers for Master Data. One per use case; validation here, business
logic in services.py (mirrors apps.accounts.settings_serializers)."""
from rest_framework import serializers

from .models import Client, Consultant, Contractor, Currency, ProjectPriority, ProjectType, SubContractor


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ["id", "code", "name", "symbol", "is_default", "sort_order", "created_at"]
        read_only_fields = ["id", "is_default", "sort_order", "created_at"]


class CurrencyCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=8)
    name = serializers.CharField(max_length=80)
    symbol = serializers.CharField(max_length=8, allow_blank=True, default="")
    is_default = serializers.BooleanField(default=False)

    def validate_code(self, value):
        return value.strip().upper()


class CurrencyUpdateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=8, required=False)
    name = serializers.CharField(max_length=80, required=False)
    symbol = serializers.CharField(max_length=8, allow_blank=True, required=False)

    def validate_code(self, value):
        return value.strip().upper()


class ProjectTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectType
        fields = ["id", "name", "sort_order", "created_at"]
        read_only_fields = ["id", "sort_order", "created_at"]


class ProjectPrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectPriority
        fields = ["id", "name", "sort_order", "created_at"]
        read_only_fields = ["id", "sort_order", "created_at"]


class NameOnlySerializer(serializers.Serializer):
    """Create/update payload shared by ProjectType and ProjectPriority — both
    are just a company-scoped name."""

    name = serializers.CharField(max_length=60)


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ["id", "name", "sort_order", "created_at"]
        read_only_fields = ["id", "sort_order", "created_at"]


class ConsultantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultant
        fields = ["id", "name", "phone", "email", "sort_order", "created_at"]
        read_only_fields = ["id", "sort_order", "created_at"]


class ContractorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contractor
        fields = ["id", "name", "phone", "email", "sort_order", "created_at"]
        read_only_fields = ["id", "sort_order", "created_at"]


class SubContractorSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubContractor
        fields = ["id", "name", "phone", "email", "sort_order", "created_at"]
        read_only_fields = ["id", "sort_order", "created_at"]


class PartyWriteSerializer(serializers.Serializer):
    """Create/update payload for a consultant or contractor. `partial` on the
    view is what makes each field optional on a PATCH, so an edit that only
    changes the phone doesn't have to resend the name."""

    name = serializers.CharField(max_length=180)
    phone = serializers.CharField(max_length=40, allow_blank=True, required=False, default="")
    email = serializers.EmailField(allow_blank=True, required=False, default="")


class ClientWriteSerializer(serializers.Serializer):
    """A client is a name and nothing else — see the model."""

    name = serializers.CharField(max_length=180)
