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
