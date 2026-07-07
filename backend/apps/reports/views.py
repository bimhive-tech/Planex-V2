"""Reports API. Company-scoped CRUD for templates + reports, plus PDF download.

Access: EXPORT_REPORTS gates everything — viewing, downloading, and editing.
Reports are sensitive deliverables, so a role without it (e.g. a site engineer)
sees no reports at all, not just a hidden download button.
"""
import json

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.constants import Permission

from .models import Report, ReportTemplate
from .pdf import build_report_pdf
from .serializers import (
    ReportListSerializer,
    ReportTemplateSerializer,
    ReportWriteSerializer,
)
from .services import build_report_context

class ReportsAccess(BasePermission):
    """EXPORT_REPORTS gates all report/template access — read, download, edit."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return Permission.EXPORT_REPORTS in user.effective_permissions()


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
    def data(self, request, pk=None):
        """The computed report data (project info + progress tables) so the
        builder can show what's pulled from the chosen project, live."""
        report = self.get_object()
        ctx = build_report_context(report)
        for key in ("logos", "photos", "attachments", "images"):
            ctx.pop(key, None)
        return Response(ctx)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Generate and stream the report PDF on demand."""
        report = self.get_object()
        ctx = build_report_context(report)
        pages = {}
        data = build_report_pdf(report, ctx, out_pages=pages)
        resp = HttpResponse(data, content_type="application/pdf")
        safe = (report.report_number or report.title or "report").replace("/", "-")
        resp["Content-Disposition"] = f'inline; filename="report-{safe}.pdf"'
        # Section -> page map so the builder tabs can scroll the preview.
        resp["X-Section-Pages"] = json.dumps(pages)
        resp["Access-Control-Expose-Headers"] = "X-Section-Pages"
        return resp
