"""Admin registration for projects (internal tooling)."""
from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "project_type", "is_archived", "created_at")
    list_filter = ("company", "project_type", "is_archived")
    search_fields = ("name", "location", "client_name")
