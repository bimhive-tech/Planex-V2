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

    class Meta:
        indexes = [models.Index(fields=["project", "sort_order"])]
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


class ProjectScope(TimestampedModel):
    """A node in a project's flexible work hierarchy
    (Phase -> Zone -> Building -> Area). Self-referencing tree."""

    class ScopeType(models.TextChoices):
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
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    scope_type = models.CharField(max_length=20, choices=ScopeType.choices)
    name = models.CharField(max_length=180)
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
