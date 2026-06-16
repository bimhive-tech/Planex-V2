"""Project serializers: list/detail/write, plus the work-hierarchy serializers."""
from rest_framework import serializers

from django.conf import settings

from .models import Activity, Project, ProjectImage, ProjectMember, ProjectScope
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
    progress_breakdown = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    team_count = serializers.SerializerMethodField()
    open_submission_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "code", "project_type", "project_type_display",
            "priority", "priority_display", "location", "description",
            "budget", "currency", *STAKEHOLDER_FIELDS, *DATE_FIELDS, "size_sqm", "notes",
            "is_archived", "overall_progress", "activity_count", "progress_breakdown",
            "manager_name", "team_count", "open_submission_count", "created_at", "updated_at",
        ]

    def get_open_submission_count(self, obj):
        from .models import ProgressSubmission
        return obj.submissions.filter(status__in=ProgressSubmission.OPEN_STATES).count()

    def get_manager_name(self, obj):
        m = next((m for m in obj.members.all() if m.role == ProjectMember.ProjectRole.MANAGER), None)
        return m.user.full_name if m else ""

    def get_team_count(self, obj):
        return obj.members.count()

    def get_overall_progress(self, obj):
        return project_overall_progress(obj)

    def get_activity_count(self, obj):
        return obj.activities.count()

    def get_progress_breakdown(self, obj):
        from django.db.models import Count, Q
        agg = obj.activities.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(progress_percent__gte=100)),
            not_started=Count("id", filter=Q(progress_percent__lte=0)),
        )
        total = agg["total"]
        return {
            "total": total,
            "completed": agg["completed"],
            "not_started": agg["not_started"],
            "in_progress": total - agg["completed"] - agg["not_started"],
        }


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


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ProjectImageSerializer(serializers.ModelSerializer):
    """Image metadata plus a private short-lived URL for preview/download."""

    url = serializers.SerializerMethodField()
    image_type_display = serializers.CharField(source="get_image_type_display", read_only=True)

    class Meta:
        model = ProjectImage
        fields = [
            "id", "image_type", "image_type_display", "caption", "sort_order",
            "url", "created_at", "updated_at",
        ]

    def get_url(self, obj):
        # Stream through the authed endpoint (works for filesystem + R2, stays
        # private). `/api` is the app's fixed proxy mount (Next rewrites it).
        if not obj.image:
            return ""
        return f"/api/projects/{obj.project_id}/images/{obj.id}/file/"


class ProjectImageUploadSerializer(serializers.ModelSerializer):
    """Validates and stores private report image assets."""

    class Meta:
        model = ProjectImage
        fields = ["image", "image_type", "caption", "sort_order"]

    def validate_image(self, value):
        if value.size > settings.MAX_UPLOAD_BYTES:
            limit = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"Image must be {limit}MB or smaller.")
        if value.content_type not in ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError("Upload a JPG, PNG, or WebP image.")
        return value


# ── Team ───────────────────────────────────────────────────────────────────
class ProjectMemberSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    user_id = serializers.CharField(source="user.id", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = ProjectMember
        fields = ["id", "user_id", "email", "full_name", "role", "role_display"]


class ProjectMemberWriteSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=ProjectMember.ProjectRole.choices,
                                   default=ProjectMember.ProjectRole.MEMBER)
