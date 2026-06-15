"""Project serializers: list/detail/write, plus the work-hierarchy serializers."""
from rest_framework import serializers

from .models import Activity, Project, ProjectScope
from .services import project_overall_progress

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
    overall_progress = serializers.SerializerMethodField()
    activity_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "code", "project_type", "project_type_display",
            "priority", "priority_display", "location", "description",
            "budget", "currency", *STAKEHOLDER_FIELDS, *DATE_FIELDS, "size_sqm", "notes",
            "is_archived", "overall_progress", "activity_count", "created_at", "updated_at",
        ]

    def get_overall_progress(self, obj):
        return project_overall_progress(obj)

    def get_activity_count(self, obj):
        return obj.activities.count()


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


# ── Work hierarchy ─────────────────────────────────────────────────────────
class ScopeSerializer(serializers.ModelSerializer):
    scope_type_display = serializers.CharField(source="get_scope_type_display", read_only=True)

    class Meta:
        model = ProjectScope
        fields = ["id", "parent", "scope_type", "scope_type_display", "name", "sort_order"]


class ScopeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectScope
        fields = ["parent", "scope_type", "name", "sort_order"]


class ActivitySerializer(serializers.ModelSerializer):
    progress_type_display = serializers.CharField(source="get_progress_type_display", read_only=True)

    class Meta:
        model = Activity
        fields = [
            "id", "scope", "name", "code", "unit", "progress_type", "progress_type_display",
            "planned_quantity", "weight", "progress_percent", "sort_order",
        ]


class ActivityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = [
            "scope", "name", "code", "unit", "progress_type",
            "planned_quantity", "weight", "progress_percent", "sort_order",
        ]

    def validate_progress_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Progress must be between 0 and 100.")
        return value
