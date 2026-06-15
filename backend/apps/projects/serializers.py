"""Project serializers: a compact list view, a full detail view, and a write view."""
from rest_framework import serializers

from .models import Project

STAKEHOLDER_FIELDS = [
    "client_name", "consultant_name", "consultant_phone", "consultant_email",
    "contractor_name", "contractor_phone", "contractor_email",
]
DATE_FIELDS = ["planned_start", "planned_finish", "revised_finish"]


class ProjectListSerializer(serializers.ModelSerializer):
    """Compact shape for the Project Hub cards."""

    project_type_display = serializers.CharField(source="get_project_type_display", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "code", "project_type", "project_type_display", "priority",
            "location", "client_name", "planned_start", "planned_finish", "is_archived",
            "created_at", "updated_at",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    project_type_display = serializers.CharField(source="get_project_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "code", "project_type", "project_type_display",
            "priority", "priority_display", "location", "description",
            "budget", "currency", *STAKEHOLDER_FIELDS, *DATE_FIELDS, "size_sqm", "notes",
            "is_archived", "created_at", "updated_at",
        ]


class ProjectWriteSerializer(serializers.ModelSerializer):
    """Create/update. `company` is set server-side; name is unique per company."""

    class Meta:
        model = Project
        fields = [
            "name", "code", "project_type", "priority", "location", "description",
            "budget", "currency", *STAKEHOLDER_FIELDS, *DATE_FIELDS, "size_sqm", "notes",
            "is_archived",
        ]

    def validate_name(self, value):
        value = value.strip()
        company = self.context["company"]
        qs = Project.objects.filter(company=company, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A project with this name already exists.")
        return value
