"""Serializers for report templates and reports."""
from rest_framework import serializers

from .constants import default_config
from .models import Report, ReportTemplate


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
            "id", "title", "report_number", "status",
            "project", "project_name", "template", "template_name",
            "period_start", "period_finish", "created_at",
        ]


class ReportWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id", "project", "template", "title", "report_number",
            "period_start", "period_finish", "status",
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
