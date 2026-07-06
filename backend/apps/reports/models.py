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
    report_date = models.DateField(null=True, blank=True)  # the report's "as-of" date
    period_start = models.DateField(null=True, blank=True)
    period_finish = models.DateField(null=True, blank=True)
    # Per-report narrative; falls back to the project's description when blank.
    # `description` is the plain-text form (search/fallback); `description_html`
    # holds the rich-text version (sanitized) the builder edits and the PDF renders.
    description = models.TextField(blank=True)
    description_html = models.TextField(blank=True)
    # Zone scope IDs to include (empty = the whole project).
    scope_ids = models.JSONField(default=list, blank=True)
    # Progress-photo IDs (from the schedule tab's submissions) chosen for the
    # report's Progress Images section. Rendered ordered by date, earliest first.
    progress_image_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="created_reports")

    class Meta:
        indexes = [models.Index(fields=["company", "project", "status"])]
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


def report_image_key(instance, filename):
    """Stable private storage key for a report's content images."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"reports/{instance.report_id}/{instance.kind}/{uuid.uuid4()}.{ext}"


class ReportImage(TimestampedModel):
    """Per-report content images: the cover, progress photos (4/page), and
    attachments (1/page). Logos stay on the project (branding is constant)."""

    class Kind(models.TextChoices):
        COVER = "cover", "Cover Image"
        PROGRESS = "progress", "Progress Photo"
        ATTACHMENT = "attachment", "Attachment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="report_images")
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=report_image_key)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PROGRESS)
    caption = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="uploaded_report_images")

    class Meta:
        indexes = [models.Index(fields=["report", "kind", "sort_order"])]
        ordering = ["kind", "sort_order", "created_at"]

    def __str__(self):
        return self.caption or self.get_kind_display()
