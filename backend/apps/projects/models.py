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


class ProgressSnapshot(TimestampedModel):
    """A dated snapshot of a project's aggregate progress, captured on each import.
    Importing monthly trackers builds a history you can chart and filter by date."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="progress_snapshots")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="snapshots")
    date = models.DateField()
    overall_progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    breakdown = models.JSONField(default=dict, blank=True)   # {total, completed, in_progress, not_started}
    zones = models.JSONField(default=list, blank=True)        # [{name, progress}]
    source = models.CharField(max_length=200, blank=True)     # e.g. the workbook file name

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "date"], name="uniq_snapshot_per_date"),
        ]
        indexes = [models.Index(fields=["project", "date"])]
        ordering = ["date"]

    def __str__(self):
        return f"{self.project.name} @ {self.date}"


class Milestone(TimestampedModel):
    """A key project milestone (kickoff, design approval, handover, ...)."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        IN_PROGRESS = "in_progress", "In Progress"
        UPCOMING = "upcoming", "Upcoming"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="milestones")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=180)
    date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPCOMING)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["project", "sort_order"])]
        ordering = ["sort_order", "date"]

    def __str__(self):
        return self.title


class ProjectMember(TimestampedModel):
    """A company user assigned to a project, with a project-level role."""

    class ProjectRole(models.TextChoices):
        MANAGER = "manager", "Project Manager"
        REVIEWER = "reviewer", "Reviewer"
        ENGINEER = "engineer", "Site Engineer"
        MEMBER = "member", "Member"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_members")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=20, choices=ProjectRole.choices, default=ProjectRole.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="uniq_project_member"),
        ]
        indexes = [models.Index(fields=["project", "role"])]
        ordering = ["role", "created_at"]

    def __str__(self):
        return f"{self.user.email} · {self.get_role_display()}"


class ProjectScope(TimestampedModel):
    """A node in a project's flexible work hierarchy
    (Phase -> Zone -> Building -> Area). Self-referencing tree."""

    class ScopeType(models.TextChoices):
        PHASE = "phase", "Phase"
        ZONE = "zone", "Zone"
        BUILDING = "building", "Building"
        AREA = "area", "Area"
        TASK = "task", "Task"

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

    # Excel-grid support. For zone trackers the tree is Zone -> Phase -> Task
    # (Task is a scope); each Activity is a (task, subzone) cell whose `scope` is
    # the Task scope and `subzone_code`/`subzone_index` place it in a grid column.
    phase_name = models.CharField(max_length=180, blank=True)
    row_index = models.PositiveIntegerField(default=0)
    subzone_code = models.CharField(max_length=80, blank=True)
    subzone_index = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["project", "scope"]),
            models.Index(fields=["scope", "subzone_index"]),
        ]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
