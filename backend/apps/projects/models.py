"""Project models. The descriptive project record (the work hierarchy — phases,
zones, activities — arrives in a later module). Company-scoped, UUID PK."""
import uuid

from django.db import models

from apps.accounts.models import Company, TimestampedModel


def source_workbook_key(instance, filename):
    """Private R2 key for a project's original imported tracker workbook, kept so
    the Primavera 'FOR (P6)' export can be returned byte-identical (only its
    progress column refreshed)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else "xlsx"
    return f"projects/{instance.id}/source/workbook.{ext}"


def p6_export_key(instance, filename):
    """Private R2 key for the generated P6 export (the refreshed workbook). These
    files are large, so generation runs in the background and the result is cached
    here until the next refresh."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else "xlsx"
    return f"projects/{instance.id}/export/p6.{ext}"


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
    # Default/fallback currency — still used as-is by other money displays
    # that only ever carry one figure for the whole project (cash flow,
    # cost performance). The 5 contract-KPI fields below (budget/advance
    # payment/contract/approved/forecast) each carry their OWN currency
    # instead: a real project can genuinely have its budget quoted in one
    # currency and, say, an advance payment paid in another — auto-
    # converting them from one shared rate would show the wrong number, not
    # just the wrong label. See each field's own `_currency` companion.
    currency = models.CharField(max_length=8, default="AED")
    budget_currency = models.CharField(max_length=8, default="AED")

    # Stakeholders (kept as fields now; a reusable Client entity comes later).
    client_name = models.CharField(max_length=180, blank=True)
    consultant_name = models.CharField(max_length=180, blank=True)
    consultant_phone = models.CharField(max_length=40, blank=True)
    consultant_email = models.EmailField(blank=True)
    contractor_name = models.CharField(max_length=180, blank=True)
    contractor_phone = models.CharField(max_length=40, blank=True)
    contractor_email = models.EmailField(blank=True)
    # A 4th party distinct from the project's own consultant — the contractor's
    # own consultant/advisor, as tracked on some contracts' progress reports.
    contractor_consultant = models.CharField(max_length=180, blank=True)

    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    # Kept in sync with the latest APPROVED schedule Variation (SVO) — see
    # apps.projects.services.resync_revised_finish. Not directly editable.
    revised_finish = models.DateField(null=True, blank=True)
    forecast_finish = models.DateField(null=True, blank=True)  # current forecast, separate from the revised baseline
    size_sqm = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    # Contract KPIs surfaced on the Overview tab (matches the client's dashboard header).
    advance_payment = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    advance_payment_currency = models.CharField(max_length=8, default="AED")
    eot_days = models.PositiveIntegerField(null=True, blank=True)  # extension of time granted, in days
    # Three distinct cost figures a report may need side by side: what was
    # signed (contract_value), what's approved after variations to date
    # (approved_value), and where it's projected to land (forecast_cost).
    # `budget` stays as the general-purpose figure other flows already use.
    contract_value = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    contract_value_currency = models.CharField(max_length=8, default="AED")
    # contract_value + the sum of all APPROVED cost Variations (CVOs) — kept in
    # sync automatically (apps.projects.services.resync_approved_value) rather
    # than hand-typed, so it can never disagree with the actual Variation log.
    # Not directly editable. Its currency always mirrors contract_value_currency
    # (a CVO amount has no currency of its own — see resync_approved_value).
    approved_value = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    approved_value_currency = models.CharField(max_length=8, default="AED")
    forecast_cost = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    forecast_cost_currency = models.CharField(max_length=8, default="AED")

    # A real P6 schedule states its own actual AND planned % complete for the
    # whole project — Performance % Complete (earned value / budgeted cost) and
    # Schedule % Complete (time-based) respectively — rather than leaving
    # Planex to approximate either. When present they're authoritative:
    # project_overall_progress() / the report's planned figure return them
    # as-is instead of recomputing, since P6's own figures already account for
    # context (critical path, resource loading) a simple formula can't fully
    # reproduce. Cleared and re-set on every import; None for projects with no
    # such source (a zone tracker, or a P6 export that didn't carry the column).
    imported_progress_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    imported_planned_progress_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    is_archived = models.BooleanField(default=False)

    # Original imported tracker workbook (.xlsm/.xlsx), retained for the P6 export.
    source_workbook = models.FileField(upload_to=source_workbook_key, null=True, blank=True)

    # Cached P6 export (the refreshed workbook) + its background-build status.
    # Generation is slow for big trackers, so it runs off the request cycle.
    class P6Status(models.TextChoices):
        IDLE = "idle", "Idle"
        GENERATING = "generating", "Generating"
        READY = "ready", "Ready"
        ERROR = "error", "Error"

    p6_export = models.FileField(upload_to=p6_export_key, null=True, blank=True)
    p6_export_status = models.CharField(max_length=12, choices=P6Status.choices, default=P6Status.IDLE)
    p6_export_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_project_name_per_company"),
        ]
        indexes = [models.Index(fields=["company", "is_archived"])]
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep approved_value correct regardless of *how* contract_value was
        # set (API, admin, import, a script) — not just the call sites that
        # remember to call this explicitly. Safe from recursion: the resync
        # persists via a queryset .update(), which doesn't invoke save().
        from .services import resync_approved_value

        resync_approved_value(self)


def project_image_key(instance, filename):
    """Stable private R2 key; never exposes a public URL."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"projects/{instance.project_id}/images/{uuid.uuid4()}.{ext}"


class ProjectImage(TimestampedModel):
    """Private image asset used by project reports: logos, cover, and site photos."""

    class ImageType(models.TextChoices):
        SITE_PHOTO = "site_photo", "Site Photo"
        COVER = "cover", "Cover Image"
        LOGO_LEFT = "logo_left", "Left Logo"
        LOGO_RIGHT = "logo_right", "Right Logo"
        # Beyond the two fixed header slots — a project can carry any number of
        # extra partner/funding/authority logos, ordered by sort_order and
        # picked in the canvas by slot index (mirrors how site photos work).
        LOGO = "logo", "Additional Logo"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_images")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=project_image_key)
    image_type = models.CharField(max_length=20, choices=ImageType.choices, default=ImageType.SITE_PHOTO)
    caption = models.CharField(max_length=180, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="uploaded_project_images")

    class Meta:
        indexes = [
            models.Index(fields=["project", "image_type", "sort_order"]),
            models.Index(fields=["company", "created_at"]),
        ]
        ordering = ["image_type", "sort_order", "created_at"]

    def __str__(self):
        return self.caption or self.get_image_type_display()


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
    # Every scope's rolled-up progress at this date ({scope_id: progress}) — lets
    # the report's hierarchy table show a "previous %" below the zone level, not
    # just at the top. Blank on snapshots taken before this existed.
    scopes = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=200, blank=True)     # e.g. the workbook file name

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "date"], name="uniq_snapshot_per_date"),
        ]
        indexes = [models.Index(fields=["project", "date"])]
        ordering = ["date"]

    def __str__(self):
        return f"{self.project.name} @ {self.date}"


class ProgressSubmission(TimestampedModel):
    """Field progress that moves through the review/approval chain. Only an
    accepted submission updates the activity's official progress."""

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending Review"
        REVIEWER_REJECTED = "reviewer_rejected", "Reviewer Rejected"
        PENDING_PM = "pending_pm", "Pending PM Approval"
        PM_REJECTED = "pm_rejected", "PM Rejected"
        ACCEPTED = "accepted", "Accepted"

    OPEN_STATES = (Status.PENDING_REVIEW, Status.PENDING_PM)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="progress_submissions")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="submissions")
    activity = models.ForeignKey("Activity", on_delete=models.CASCADE, related_name="submissions")

    submitted_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="submitted_progress")
    reviewed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_progress")
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_progress")

    previous_progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    submitted_progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_REVIEW)
    note = models.TextField(blank=True)            # submitter note
    review_comment = models.TextField(blank=True)  # reviewer/PM comment (required on reject)
    # Per-stage timestamps for the audit trail (created_at is the submit time).
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["activity", "status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.activity.name} → {self.submitted_progress}% ({self.get_status_display()})"


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

    # Set only when a P6 import's "Activity % Complete" column has a real
    # value for this row — null (not 0) for a manually added milestone or a
    # row the source file left blank, so the UI can tell "0% complete" apart
    # from "no figure to show" instead of assuming zero.
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Set only when a P6 import's Planex Code ties the milestone to a specific
    # zone/building (e.g. a per-building handover date) — null for project-wide
    # milestones (kickoff, overall handover) and any manually added one.
    scope = models.ForeignKey(
        "ProjectScope", on_delete=models.SET_NULL, null=True, blank=True, related_name="milestones",
    )

    class Meta:
        indexes = [models.Index(fields=["project", "sort_order"]), models.Index(fields=["project", "scope"])]
        ordering = ["sort_order", "date"]

    def __str__(self):
        return self.title


class ProjectDelay(TimestampedModel):
    """A delay / obstacle on a project (the report's «المعوقات» section)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_delays")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="delays")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    impact_days = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    date = models.DateField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["project", "sort_order"])]
        ordering = ["sort_order", "-date"]

    def __str__(self):
        return self.title


class PartScope(TimestampedModel):
    """A specific contracted "Part" (sub-scope) of the work, tracked in
    parallel with the whole project — its own amount, start date, and
    completion baseline/forecast. A log, not a single snapshot: a project
    can have more than one entry over its life (a new Part added later, or
    one superseded by a revision), so past ones stay visible instead of
    being silently overwritten. The report shows the most recent entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="part_scopes")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="part_scopes")
    title = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    completion_revised = models.DateField(null=True, blank=True)  # revised baseline completion
    forecast_completion = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_part_scopes")

    class Meta:
        indexes = [models.Index(fields=["project", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def delay_days(self) -> int | None:
        if self.forecast_completion is None or self.completion_revised is None:
            return None
        return (self.forecast_completion - self.completion_revised).days


class ProjectMember(TimestampedModel):
    """A company user assigned to a project. What they can DO comes from their
    company role (Settings -> Permissions); what part of the project they can
    SEE comes from their scope grants (ProjectScopeAccess) below."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_members")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="project_memberships")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="uniq_project_member"),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return self.user.email


class ProjectScopeAccess(TimestampedModel):
    """Restricts a member to specific scopes (zones). Following Planex: a user with
    NO grants sees the whole project; grants narrow them to those zones."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="scope_access")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scope_access")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="project_scope_access")
    scope = models.ForeignKey("ProjectScope", on_delete=models.CASCADE, related_name="access_grants")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user", "scope"], name="uniq_scope_access"),
        ]
        indexes = [models.Index(fields=["project", "user"])]

    def __str__(self):
        return f"{self.user.email} → {self.scope.name}"


def schedule_import_file_key(instance, filename):
    """Private R2 key for one retained schedule-import workbook — keyed by the
    import's own id (not the project's), unlike `source_workbook_key`, so
    re-importing doesn't overwrite the previous file. Every past import's
    workbook stays downloadable."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else "xlsx"
    return f"projects/{instance.project_id}/schedule-imports/{instance.id}.{ext}"


class ScheduleImport(TimestampedModel):
    """One schedule import, as its own permanently-retained batch.

    Before this model existed, every re-import called `project.scopes.all().
    delete()` and rebuilt from scratch — so only ever one generation of
    Scope/Activity data existed for a project at a time, and a re-import
    silently erased the previous one down to the individual activity. That's
    what `ProgressSnapshot` was for: capturing a *rolled-up* history (overall
    %, per-zone %) across imports. It never captured the full activity-level
    detail (budgeted cost, earned value, individual activity progress, ...) —
    exactly the data the report's BOQ/financial charts depend on.

    Every `ProjectScope`/`Activity` row now carries a `schedule_import` FK to
    the batch it came from, and a re-import creates a NEW batch instead of
    deleting the old one — every past import's full data stays queryable,
    not just its summary. "Current" is simply the most recent batch by
    `date` (see `apps.projects.services.latest_schedule_import`); picking an
    older one is a query, not a recovery.

    `date` is the schedule's own as-of date (parsed from the filename, or
    explicitly chosen at upload) — the date the DATA reflects, not
    necessarily when it was uploaded."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="schedule_imports")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="schedule_imports")
    date = models.DateField()
    source = models.CharField(max_length=200, blank=True)  # original filename
    file = models.FileField(upload_to=schedule_import_file_key, null=True, blank=True)
    activity_count = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="schedule_imports")

    class Meta:
        indexes = [models.Index(fields=["project", "-date"])]
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.project_id} @ {self.date}"


class ProjectScope(TimestampedModel):
    """A node in a project's flexible work hierarchy
    (Phase -> Zone -> Building -> Area). Self-referencing tree."""

    class ScopeType(models.TextChoices):
        STAGE = "stage", "Stage"      # a top-level grouping above zones (e.g. a P6 project stage)
        PHASE = "phase", "Phase"
        ZONE = "zone", "Zone"
        BUILDING = "building", "Building"
        AREA = "area", "Area"
        TASK = "task", "Task"

    class Discipline(models.TextChoices):
        CONCRETE = "concrete", "Concrete"
        ARCHITECTURE = "architecture", "Architecture"
        ELECTRICAL = "electrical", "Electrical"
        MECHANICAL = "mechanical", "Mechanical"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_scopes")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scopes")
    # Which import batch this node came from — see ScheduleImport's own
    # docstring. Nullable only for rows created by hand (the "Add scope"
    # form has no import to attach to); every imported row always has one.
    schedule_import = models.ForeignKey(
        "ScheduleImport", on_delete=models.CASCADE, null=True, blank=True, related_name="scopes")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    scope_type = models.CharField(max_length=20, choices=ScopeType.choices)
    # Stable grouping/matching key — for a code-driven P6 import this is the
    # raw Planex Code segment (e.g. "PH1", "Z(A)", "Building 15"), used to
    # resolve milestone scope links and to re-key nodes across an import.
    # Never shown to a user on its own; see `label`.
    name = models.CharField(max_length=180)
    # Human-readable display text read from the source file's own WBS heading
    # (e.g. "المرحلة الاولي (75 عمارة)" for "PH1") when a code-driven import
    # can determine one — blank otherwise, in which case the UI falls back to
    # `name` (already human-readable for the older indentation-only import
    # scheme, and for anything created by hand). Purely cosmetic: nothing
    # matches or re-imports by this field, only by `name`, so it changing (or
    # being blank) between imports never affects import correctness.
    label = models.CharField(max_length=180, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    # Optional own schedule (any node may carry one, independent of the
    # project's dates) — backs per-area duration/time-performance and the
    # Gantt-style report section. Blank = falls back to the project's dates.
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    revised_finish = models.DateField(null=True, blank=True)

    # Trade tag — meaningful on a Phase node (a zone-tracker phase usually IS
    # one trade's work package); lets the report split one building's progress
    # into Concrete/Architecture/Electrical/Mechanical columns without adding
    # another tree level. Blank = unclassified.
    discipline = models.CharField(max_length=20, choices=Discipline.choices, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["project", "parent"]),
            models.Index(fields=["project", "schedule_import"]),
        ]
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
    # Denormalized from scope.schedule_import (not just reachable via the FK)
    # so the heavy, frequent "current activities" queries — full-table
    # aggregates over tens of thousands of rows — filter directly without an
    # extra join. Kept in sync at creation time only; activities are never
    # moved between imports.
    schedule_import = models.ForeignKey(
        "ScheduleImport", on_delete=models.CASCADE, null=True, blank=True, related_name="activities")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=60, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    progress_type = models.CharField(max_length=20, choices=ProgressType.choices, default=ProgressType.PERCENTAGE)
    planned_quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Roll-up lever. A zone tracker fills this from its "W" column; a P6 import
    # fills it with the activity's budgeted cost, which is what makes our overall
    # % match P6's own Performance % Complete. Cost figures run to billions, so
    # this is far wider than a hand-entered weight would need.
    weight = models.DecimalField(max_digits=18, decimal_places=2, default=1)
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

    # A real P6 schedule import gives each activity its own dates (unlike a zone
    # tracker cell, which only has a phase-level date via its parent scope).
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)

    # Cost + schedule columns carried by a P6 export. Null for imports that have
    # no such data (zone trackers), so "no value" stays distinct from "zero".
    budgeted_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    earned_value_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    schedule_variance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_float = models.IntegerField(null=True, blank=True)  # days of slack; <=0 is on the critical path
    original_duration = models.IntegerField(null=True, blank=True)
    remaining_duration = models.IntegerField(null=True, blank=True)
    baseline_duration = models.IntegerField(null=True, blank=True)  # P6 "BL Project Duration"
    actual_duration = models.IntegerField(null=True, blank=True)
    schedule_performance_index = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)

    @property
    def is_critical(self) -> bool:
        """P6 treats an activity with no slack left as critical — any slip on it
        slips the project finish."""
        return self.total_float is not None and self.total_float <= 0

    class Meta:
        indexes = [
            models.Index(fields=["project", "scope"]),
            models.Index(fields=["scope", "subzone_index"]),
            models.Index(fields=["project", "schedule_import"]),
        ]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


def progress_image_key(instance, filename):
    """Stable private storage key for a progress-update photo."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"projects/{instance.entry.project_id}/progress/{uuid.uuid4()}.{ext}"


class ProgressEntry(TimestampedModel):
    """A dated progress reading for one activity — the history behind the activity's
    current %. Lets us report 'as of' any date and revise a past date."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="progress_entries")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="progress_entries")
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="progress_entries")
    date = models.DateField()  # the date the progress is recorded FOR (<= today)
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="progress_entries")

    class Meta:
        indexes = [
            models.Index(fields=["activity", "date"]),
            models.Index(fields=["project", "date"]),
        ]
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.activity.name} = {self.progress_percent}% @ {self.date}"


class ProgressImage(TimestampedModel):
    """A photo attached to a progress entry (inherits the entry's activity + date).
    Optional caption; removable by users with the manage-progress-media permission."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="progress_images")
    entry = models.ForeignKey(ProgressEntry, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=progress_image_key)
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="uploaded_progress_images")

    class Meta:
        indexes = [models.Index(fields=["entry", "created_at"])]
        ordering = ["created_at"]

    def __str__(self):
        return self.caption or "progress photo"


def submission_image_key(instance, filename):
    """Stable private storage key for a submission's supporting photo."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"projects/{instance.submission.project_id}/submissions/{uuid.uuid4()}.{ext}"


class SubmissionImage(TimestampedModel):
    """A photo attached as evidence to a progress submission (separate from
    ProgressEntry photos — this is evidence for the review/approval chain, not
    the accepted history). Optional caption."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="submission_images")
    submission = models.ForeignKey(ProgressSubmission, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=submission_image_key)
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="uploaded_submission_images")

    class Meta:
        indexes = [models.Index(fields=["submission", "created_at"])]
        ordering = ["created_at"]

    def __str__(self):
        return self.caption or "submission photo"


class CashFlowEntry(TimestampedModel):
    """One month's planned vs actual cash for a project. The user enters both
    numbers (we don't compute them); the report charts them as-is and can add
    them up for a cumulative S-curve."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="cashflow_entries")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="cashflow_entries")
    month = models.DateField()  # first day of the month it represents
    planned = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    actual = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "month"], name="uniq_cashflow_month"),
        ]
        indexes = [models.Index(fields=["project", "month"])]
        ordering = ["month"]

    def __str__(self):
        return f"{self.project_id} {self.month:%Y-%m}"


def invoice_image_key(instance, filename):
    """Stable private R2 key for an invoice scan/photo."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"projects/{instance.project_id}/invoices/{uuid.uuid4()}.{ext}"


class Invoice(TimestampedModel):
    """A project invoice / extract (مستخلص): a value, a name/reason, and an
    optional scan. Surfaced in the report's invoices section."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invoices")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invoices")
    name = models.CharField(max_length=200)  # reason / title of the invoice
    value = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    date = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to=invoice_image_key, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="created_invoices")

    class Meta:
        indexes = [
            models.Index(fields=["project", "sort_order"]),
            models.Index(fields=["project", "-date"]),
        ]
        ordering = ["sort_order", "-date", "-created_at"]

    def __str__(self):
        return self.name


def submittal_attachment_key(instance, filename):
    """Stable private R2 key for a submittal attachment (drawing/PDF/image)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"projects/{instance.project_id}/submittals/{uuid.uuid4()}.{ext}"


class Submittal(TimestampedModel):
    """A shop-drawing or material submittal and its approval status (the report's
    «موقف الرسومات / موقف اعتماد المواد» section)."""

    class Type(models.TextChoices):
        SHOP_DRAWING = "shop_drawing", "Shop Drawing"
        MATERIAL = "material", "Material"

    class Discipline(models.TextChoices):
        CONCRETE = "concrete", "Concrete"
        ARCHITECTURE = "architecture", "Architecture"
        ELECTRICAL = "electrical", "Electrical"
        MECHANICAL = "mechanical", "Mechanical"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        APPROVED_WITH_COMMENTS = "approved_with_comments", "Approved with comments"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="submittals")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="submittals")
    title = models.CharField(max_length=200)
    submittal_type = models.CharField(max_length=20, choices=Type.choices, default=Type.SHOP_DRAWING)
    discipline = models.CharField(max_length=20, choices=Discipline.choices, default=Discipline.OTHER)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=80, blank=True)
    date = models.DateField(null=True, blank=True)  # submission date
    attachment = models.FileField(upload_to=submittal_attachment_key, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="created_submittals")

    class Meta:
        indexes = [
            models.Index(fields=["project", "sort_order"]),
            models.Index(fields=["project", "status"]),
        ]
        ordering = ["sort_order", "-date", "-created_at"]

    def __str__(self):
        return self.title


class Variation(TimestampedModel):
    """A Variation Order against the project baseline. A SCHEDULE variation (SVO)
    proposes a new finish date (e.g. an extension of time from a payment delay);
    a COST variation (CVO) proposes a contract-value change. Each is auto-numbered
    per project per kind and moves through Pending → Approved / Rejected — the
    effect (finish date / contract value) only applies once APPROVED."""

    class Kind(models.TextChoices):
        SCHEDULE = "schedule", "Schedule"
        COST = "cost", "Cost"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    # Prefix for the auto-assigned number, by kind (SVO-001, CVO-001, ...).
    NUMBER_PREFIX = {Kind.SCHEDULE: "SVO", Kind.COST: "CVO"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="variations")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="variations")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    number = models.CharField(max_length=20, blank=True)  # auto: SVO-003 / CVO-002
    title = models.CharField(max_length=200)
    reason = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)  # when approved/rejected
    decided_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="decided_variations")

    # SCHEDULE: the finish date this VO proposes, plus a snapshot of the finish it
    # replaced (captured at approval, so the log reads "from X to Y"). Days derived.
    previous_finish = models.DateField(null=True, blank=True)
    new_finish = models.DateField(null=True, blank=True)

    # COST: signed change to the contract value (+ added work, − omitted work).
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="created_variations")

    class Meta:
        indexes = [models.Index(fields=["project", "kind", "status"])]
        ordering = ["-created_at"]

    def __str__(self):
        return self.number or self.title


class Notification(TimestampedModel):
    """A per-user, in-app notification raised by the approval workflow.

    Denormalises the human-readable message + project link so it survives the
    referenced submission being deleted, and stays cheap to list."""

    class Kind(models.TextChoices):
        SUBMITTED = "submitted", "Submitted for review"
        REVIEW_APPROVED = "review_approved", "Awaiting your approval"
        REVIEW_REJECTED = "review_rejected", "Rejected by reviewer"
        ACCEPTED = "accepted", "Accepted"
        PM_REJECTED = "pm_rejected", "Rejected by approver"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="triggered_notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="notifications")
    submission = models.ForeignKey("ProgressSubmission", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="notifications")
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} -> {self.recipient_id}"
