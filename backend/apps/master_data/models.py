"""Company-editable dropdown lists ("Master Data"): currencies, project types,
and project priorities. Each Project stores the chosen value as a plain string
(no FK — matches how currency has always worked), so these tables exist only
to drive the dropdowns and let a company curate its own list; they never
constrain what a Project can already hold.
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
