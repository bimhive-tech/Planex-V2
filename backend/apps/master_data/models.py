"""Company-editable dropdown lists ("Master Data"): currencies, project types,
project priorities, and one roster of parties — the companies a project names
as its owner, consultant, contractor or sub-contractor. Each Project stores the
chosen value as a plain string (no FK — matches how currency has always
worked), so these tables exist only to drive the dropdowns and let a company
curate its own list; they never constrain what a Project can already hold.
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


class Party(TimestampedModel):
    """One company a project can name, in any role.

    Owner, consultant, contractor and sub-contractor used to be four separate
    tables, on the reasoning that they were separately-curated lists that only
    happened to look alike. In practice they are one roster of firms wearing
    different hats: the planners kept entering the same company four times, and
    the same firm is routinely the main contractor on one project and the
    consultant or a sub-contractor on another (client ask, 2026-09-13). A role
    belongs to the project-party pairing, not to the company, so it is stored
    where the pairing is -- on the Project's own `*_name` field.

    Nothing here constrains a Project. Each Project still stores the chosen
    name as a plain string, so this table only drives the dropdowns and lets a
    company curate its own roster; a rename is carried onto the projects using
    it (see services.update_party), which is now every role at once rather than
    just the one list the name happened to be filed under.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="parties")
    name = models.CharField(max_length=180)  # stored verbatim on the Project
    # Picking a party in the project form fills these in alongside the name,
    # which is the whole reason they live here rather than being retyped per
    # project. Owners had no contact fields when they were their own list;
    # merging gives them the same ones as everyone else.
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_party_per_company"),
        ]
        ordering = ["sort_order", "name"]
        verbose_name_plural = "parties"

    def __str__(self):
        return f"{self.name} ({self.company.name})"
