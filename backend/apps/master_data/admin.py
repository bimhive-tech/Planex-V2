"""Admin registrations for master_data."""
from django.contrib import admin

from .models import Currency, ProjectPriority, ProjectType


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "company", "is_default", "sort_order"]
    list_filter = ["company", "is_default"]


@admin.register(ProjectType)
class ProjectTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "sort_order"]
    list_filter = ["company"]


@admin.register(ProjectPriority)
class ProjectPriorityAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "sort_order"]
    list_filter = ["company"]
