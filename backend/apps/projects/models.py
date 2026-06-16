"""Project models. The descriptive project record (the work hierarchy — phases,
zones, activities — arrives in a later module). Company-scoped, UUID PK."""
import uuid

from django.db import models

from apps.accounts.models import Company, TimestampedModel


class Project(TimestampedModel):
    class ProjectType(models.TextChoices):
        COMMERCIAL = "commercial", "Commercial"
        RESIDENTIAL = "residential", "Residential"
        INFRASTRUCTURE = "infrastructure", "Infrastructure"
        INDUSTRIAL = "industrial", "Industrial"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=60, blank=True)  # e.g. SCD-2026-001
    project_type = models.CharField(max_length=40, choices=ProjectType.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    location = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)

    # Budget (optional). Money uses DecimalField, never float.
    budget = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="AED")

    # Stakeholders (kept as fields now; a reusable Client entity comes later).
    client_name = models.CharField(max_length=180, blank=True)
    consultant_name = models.CharField(max_length=180, blank=True)
    consultant_phone = models.CharField(max_length=40, blank=True)
    consultant_email = models.EmailField(blank=True)
    contractor_name = models.CharField(max_length=180, blank=True)
    contractor_phone = models.CharField(max_length=40, blank=True)
    contractor_email = models.EmailField(blank=True)

    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    revised_finish = models.DateField(null=True, blank=True)
    size_sqm = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    is_archived = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_project_name_per_company"),
        ]
        indexes = [models.Index(fields=["company", "is_archived"])]
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProjectScope(TimestampedModel):
    """A node in a project's flexible work hierarchy
    (Phase -> Zone -> Building -> Area). Self-referencing tree."""

    class ScopeType(models.TextChoices):
        PHASE = "phase", "Phase"
        ZONE = "zone", "Zone"
        BUILDING = "building", "Building"
        AREA = "area", "Area"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_scopes")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scopes")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    scope_type = models.CharField(max_length=20, choices=ScopeType.choices)
    name = models.CharField(max_length=180)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["project", "parent"])]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.get_scope_type_display()}: {self.name}"


class Activity(TimestampedModel):
    """A BOQ item / activity — the leaf where progress is tracked. Percentage- or
    quantity-based (fixed at setup). Carries a weight used for roll-up."""

    class ProgressType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        QUANTITY = "quantity", "Quantity"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="activities")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="activities")
    scope = models.ForeignKey(ProjectScope, on_delete=models.CASCADE, related_name="activities")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=60, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    progress_type = models.CharField(max_length=20, choices=ProgressType.choices, default=ProgressType.PERCENTAGE)
    planned_quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    # Actual completion 0–100. (Interim: set directly; the review/approval chain
    # that feeds "accepted" progress is a later module.)
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sort_order = models.PositiveIntegerField(default=0)

    # Excel-grid support: a zone tracker stores one Activity per (task, subzone)
    # cell. `row_index` identifies the task row (same value across its subzones)
    # and `phase_name` groups task rows into sections.
    phase_name = models.CharField(max_length=180, blank=True)
    row_index = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["project", "scope"]),
            models.Index(fields=["scope", "row_index"]),
        ]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
