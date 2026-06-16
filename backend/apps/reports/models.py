"""Report templates (styling/layout config) and generated reports."""
import uuid

from django.db import models

from apps.accounts.models import Company, TimestampedModel
from apps.projects.models import Project

from .constants import default_config


class ReportTemplate(TimestampedModel):
    """A company-scoped, fully configurable report design (cover, fonts, colors,
    TOC, sections, tables). The `config` JSON holds every knob — see constants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="report_templates")
    name = models.CharField(max_length=180)
    config = models.JSONField(default=default_config, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_report_template_per_company"),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Report(TimestampedModel):
    """A generated report for a project over a period, rendered with a template."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="reports")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="reports")
    template = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")

    title = models.CharField(max_length=200)
    report_number = models.CharField(max_length=60, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_finish = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="created_reports")

    class Meta:
        indexes = [models.Index(fields=["company", "project", "status"])]
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
