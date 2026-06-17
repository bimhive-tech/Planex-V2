"""Serializers for report templates and reports."""
from django.conf import settings
from rest_framework import serializers

from .constants import default_config
from .models import Report, ReportImage, ReportTemplate

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ReportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportTemplate
        fields = ["id", "name", "config", "is_default", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_config(self, value):
        if value in (None, ""):
            return default_config()
        if not isinstance(value, dict):
            raise serializers.ValidationError("Config must be an object.")
        return value


class ReportListSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True, default=None)

    class Meta:
        model = Report
        fields = [
            "id", "title", "report_number", "report_date", "status",
            "project", "project_name", "template", "template_name",
            "period_start", "period_finish", "description", "scope_ids", "created_at",
        ]


class ReportWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id", "project", "template", "title", "report_number", "report_date",
            "period_start", "period_finish", "description", "scope_ids", "status",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        """Project and template must belong to the caller's company."""
        company = self.context["request"].user.company
        project = attrs.get("project") or getattr(self.instance, "project", None)
        if project and project.company_id != company.id:
            raise serializers.ValidationError({"project": "Project not found."})
        template = attrs.get("template")
        if template and template.company_id != company.id:
            raise serializers.ValidationError({"template": "Template not found."})
        return attrs


class ReportImageSerializer(serializers.ModelSerializer):
    """Per-report image metadata + a private streamed URL."""

    url = serializers.SerializerMethodField()
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = ReportImage
        fields = ["id", "kind", "kind_display", "caption", "sort_order", "url", "created_at"]

    def get_url(self, obj):
        if not obj.image:
            return ""
        return f"/api/reports/{obj.report_id}/images/{obj.id}/file/"


class ReportImageUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportImage
        fields = ["image", "kind", "caption", "sort_order"]

    def validate_image(self, value):
        if value.size > settings.MAX_UPLOAD_BYTES:
            limit = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"Image must be {limit}MB or smaller.")
        if getattr(value, "content_type", None) not in ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError("Upload a JPG, PNG, or WebP image.")
        return value
