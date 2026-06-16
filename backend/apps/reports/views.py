"""Reports API. Company-scoped CRUD for templates + reports, plus PDF download.

Access: VIEW_PROJECTS to read, EXPORT_REPORTS to create/edit/generate.
"""
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.constants import Permission

from .models import Report, ReportTemplate
from .pdf import build_report_pdf
from .serializers import (
    ReportListSerializer,
    ReportTemplateSerializer,
    ReportWriteSerializer,
)
from .services import build_report_context

READ_ACTIONS = {"list", "retrieve", "pdf"}


class ReportsAccess(BasePermission):
    """VIEW_PROJECTS for reads; EXPORT_REPORTS for writes/generation."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        perms = user.effective_permissions()
        if view.action in READ_ACTIONS:
            return bool({Permission.VIEW_PROJECTS, Permission.EXPORT_REPORTS} & perms)
        return Permission.EXPORT_REPORTS in perms


class ReportTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReportsAccess]
    serializer_class = ReportTemplateSerializer

    def get_queryset(self):
        return ReportTemplate.objects.filter(company=self.request.user.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class ReportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReportsAccess]

    def get_queryset(self):
        qs = Report.objects.filter(company=self.request.user.company).select_related(
            "project", "template"
        )
        if self.action == "list":
            project = self.request.query_params.get("project")
            if project:
                qs = qs.filter(project_id=project)
        return qs

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ReportWriteSerializer
        return ReportListSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Generate and stream the report PDF on demand."""
        report = self.get_object()
        ctx = build_report_context(report)
        data = build_report_pdf(report, ctx)
        resp = HttpResponse(data, content_type="application/pdf")
        safe = (report.report_number or report.title or "report").replace("/", "-")
        resp["Content-Disposition"] = f'inline; filename="report-{safe}.pdf"'
        return resp
