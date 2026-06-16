"""Admin registrations for reports."""
from django.contrib import admin

from .models import Report, ReportTemplate


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "is_default", "updated_at"]
    list_filter = ["company", "is_default"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["title", "project", "report_number", "status", "created_at"]
    list_filter = ["company", "status"]
