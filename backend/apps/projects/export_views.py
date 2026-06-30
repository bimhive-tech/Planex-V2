"""Project data export endpoints.

Two cases for the P6 export:
  * No original workbook on file -> generate a light P6-shaped sheet synchronously
    (fast) and stream it.
  * Original workbook on file -> return it with only the '% Complete' column
    refreshed. That file is huge (tens of thousands of rows + macros), so it's
    built in a BACKGROUND thread and cached; the client prepares, polls, then
    downloads.
"""
import threading

from django.core.files.base import ContentFile
from django.db import connection
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .exports import build_p6_workbook, refresh_source_workbook
from .models import Project

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLSM_MIME = "application/vnd.ms-excel.sheet.macroEnabled.12"
# A generation running longer than this is treated as dead and may be restarted.
_STALE_AFTER = timezone.timedelta(minutes=15)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in name).strip() or "project"


def _get_project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_export(request):
    perms = request.user.effective_permissions()
    if Permission.EXPORT_REPORTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
        raise PermissionDenied("You don't have permission to export this project.")


def _generate_p6(project_id):
    """Background worker: build the refreshed workbook and cache it on the project."""
    try:
        project = Project.objects.get(pk=project_id)
        result = refresh_source_workbook(project)
        if result is None:
            project.p6_export_status = Project.P6Status.ERROR
            project.save(update_fields=["p6_export_status", "updated_at"])
            return
        content, filename = result
        project.p6_export.save(filename, ContentFile(content), save=False)
        project.p6_export_status = Project.P6Status.READY
        project.save(update_fields=["p6_export", "p6_export_status", "updated_at"])
    except Exception:
        Project.objects.filter(pk=project_id).update(p6_export_status=Project.P6Status.ERROR)
    finally:
        connection.close()  # this thread owns its DB connection


def _start_generation(project):
    project.p6_export_status = Project.P6Status.GENERATING
    project.p6_export_started_at = timezone.now()
    project.save(update_fields=["p6_export_status", "p6_export_started_at", "updated_at"])
    threading.Thread(target=_generate_p6, args=(project.id,), daemon=True).start()


class ProjectP6PrepareView(APIView):
    """POST to (re)build the P6 export. Returns the delivery mode + current status.
    'instant' means there's no stored workbook, so the client can download directly."""

    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        project = _get_project(request, project_id)
        _require_export(request)

        if not project.source_workbook:
            return Response({"mode": "instant"})

        st = project.p6_export_status
        generating = (st == Project.P6Status.GENERATING and project.p6_export_started_at
                      and timezone.now() - project.p6_export_started_at < _STALE_AFTER)
        if not generating:
            # Always rebuild on prepare so the export reflects the latest progress.
            _start_generation(project)
        return Response({"mode": "background", "status": Project.P6Status.GENERATING})


class ProjectP6StatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _get_project(request, project_id)
        _require_export(request)
        ready = bool(project.p6_export) and project.p6_export_status == Project.P6Status.READY
        return Response({"status": project.p6_export_status, "ready": ready})


class ProjectP6ExportView(APIView):
    """GET the P6 file. Streams the light generated sheet when there's no stored
    workbook; otherwise streams the cached refreshed workbook (409 if not ready)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _get_project(request, project_id)
        _require_export(request)

        if not project.source_workbook:
            content = build_p6_workbook(project)
            return self._file(content, f"{project.name} - P6 export.xlsx", _XLSX_MIME)

        if project.p6_export and project.p6_export_status == Project.P6Status.READY:
            content = project.p6_export.read()
            name = project.p6_export.name
            mime = _XLSM_MIME if name.lower().endswith(".xlsm") else _XLSX_MIME
            ext = "xlsm" if name.lower().endswith(".xlsm") else "xlsx"
            return self._file(content, f"{project.name} - FOR (P6).{ext}", mime)

        return Response({"status": project.p6_export_status, "ready": False},
                        status=http_status.HTTP_409_CONFLICT)

    @staticmethod
    def _file(content, filename, mime):
        response = HttpResponse(content, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="{_safe(filename)}"'
        return response
