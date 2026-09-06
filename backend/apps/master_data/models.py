"""Company-editable dropdown lists ("Master Data"): currencies, project types,
project priorities, and the stakeholder lists (clients, consultants,
contractors, subcontractors). Each Project stores the chosen value as a plain string (no FK —
matches how currency has always worked), so these tables exist only to drive
the dropdowns and let a company curate its own list; they never constrain what
a Project can already hold.
"""
import uuid

from django.db import models

from apps.accounts.models import Company, TimestampedModel


class Currency(TimestampedModel):
    """A currency a company can select for a project's budget."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="currencies")
    code = models.CharField(max_length=8)  # e.g. "AED" — what's stored on Project.currency
    name = models.CharField(max_length=80)  # e.g. "UAE Dirham"
    symbol = models.CharField(max_length=8, blank=True)  # e.g. "$"
    is_default = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_currency_code_per_company"),
        ]
        ordering = ["sort_order", "code"]
        verbose_name_plural = "currencies"

    def __str__(self):
        return f"{self.code} ({self.company.name})"


class ProjectType(TimestampedModel):
    """A project type option (stored verbatim on Project.project_type)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_types")
    name = models.CharField(max_length=60)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_project_type_per_company"),
        ]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class ProjectPriority(TimestampedModel):
    """A project priority option (stored verbatim on Project.priority)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_priorities")
    name = models.CharField(max_length=60)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_project_priority_per_company"),
        ]
        ordering = ["sort_order", "name"]
        verbose_name_plural = "project priorities"

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class _Party(TimestampedModel):
    """Shared shape for the stakeholder lists below.

    Abstract, not one table with a "role" column: a company's clients,
    consultants and contractors are three separately-curated lists that happen
    to look alike, and each maps to its own Project field (`client_name`,
    `consultant_name`, `contractor_name`). One shared table would make
    "rename this consultant" quietly able to collide with a client of the same
    name, and every query would need a role filter for no gain.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)  # stored verbatim on the Project
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class Client(_Party):
    """A client a project can be for (stored on Project.client_name)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="clients")

    class Meta(_Party.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_client_per_company"),
        ]


class _ContactParty(_Party):
    """A party the project also records a phone/email for. Picking one in the
    project form fills those in alongside the name, which is the whole reason
    they live here rather than being retyped per project."""

    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)

    class Meta(_Party.Meta):
        abstract = True


class Consultant(_ContactParty):
    """A consultant (stored on Project.consultant_name, and reused for
    Project.contractor_consultant — that field names a consultant too)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="consultants")

    class Meta(_ContactParty.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_consultant_per_company"),
        ]


class Contractor(_ContactParty):
    """A contractor (stored on Project.contractor_name)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="contractors")

    class Meta(_ContactParty.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_contractor_per_company"),
        ]


class SubContractor(_ContactParty):
    """A subcontractor (stored on Project.subcontractor_name). Its own list
    rather than a reuse of Contractor: the same firm can be a main contractor
    on one project and a subcontractor on another, and a company curates the
    two rosters separately."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="subcontractors")

    class Meta(_ContactParty.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_subcontractor_per_company"),
        ]
