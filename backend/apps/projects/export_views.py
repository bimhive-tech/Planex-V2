"""Project data export endpoints. The P6 export streams a generated .xlsx of the
project's activities + accepted progress (see exports.build_p6_workbook)."""
from django.http import HttpResponse
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .exports import build_p6_workbook
from .models import Project

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_filename(name: str) -> str:
    base = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "project"
    return f"{base} - P6 export.xlsx"


class ProjectP6ExportView(APIView):
    """GET an .xlsx of the project's activities + accepted progress, P6-style."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        try:
            project = Project.objects.get(pk=project_id, company=request.user.company)
        except (Project.DoesNotExist, ValueError, TypeError):
            raise NotFound("Project not found.")

        perms = request.user.effective_permissions()
        if Permission.EXPORT_REPORTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
            raise PermissionDenied("You don't have permission to export this project.")

        content = build_p6_workbook(project)
        response = HttpResponse(content, content_type=_XLSX_MIME)
        response["Content-Disposition"] = f'attachment; filename="{_safe_filename(project.name)}"'
        return response
