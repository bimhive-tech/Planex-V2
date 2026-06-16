"""Work-hierarchy API: read the project structure tree, and CRUD scopes/activities.

Routes are nested under a project. Reads need VIEW_PROJECTS; writes need
MANAGE_PROJECTS. Everything is company- and project-scoped (tenant isolation).
"""
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .imports import import_workbook
from .models import Activity, Project, ProjectScope
from .serializers import (
    ActivitySerializer,
    ActivityWriteSerializer,
    ScopeSerializer,
    ScopeWriteSerializer,
)
from .services import project_overall_progress, scope_progress_map


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require(request, perm):
    perms = request.user.effective_permissions()
    if perm not in perms:
        raise PermissionDenied("You don't have permission to do that.")


def _require_view(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_PROJECTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
        raise PermissionDenied("You don't have permission to view this.")


def _validate_parent(project, parent):
    if parent and parent.project_id != project.id:
        raise ValidationError({"parent": "Parent scope belongs to another project."})


# Above this many activities (zone trackers), the tree omits the activity list —
# they're viewed/edited per-zone in the Excel grid instead.
ACTIVITY_INLINE_LIMIT = 600


class ProjectStructureView(APIView):
    """GET the scope tree + rolled-up progress. Activities are inlined only for
    small (manually-built) structures; large zone imports use the grid view."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        scopes = project.scopes.all()
        activity_count = project.activities.count()
        inline = activity_count <= ACTIVITY_INLINE_LIMIT
        return Response({
            "overall_progress": project_overall_progress(project),
            "scope_progress": scope_progress_map(project),
            "scopes": ScopeSerializer(scopes, many=True).data,
            "activities": ActivitySerializer(project.activities.all(), many=True).data if inline else [],
            "activity_count": activity_count,
            "activities_inlined": inline,
        })


class ProjectZoneGridView(APIView):
    """GET the Excel-style matrix for one zone: subzones (columns) x tasks (rows),
    each cell an activity's progress."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, zone_id):
        project = _project(request, project_id)
        _require_view(request)
        try:
            zone = ProjectScope.objects.get(pk=zone_id, project=project)
        except (ProjectScope.DoesNotExist, ValueError, TypeError):
            raise NotFound("Zone not found.")

        # Tree is Zone -> Phase -> Task; each task carries (subzone) cells. Rows are
        # the task scopes; columns are the distinct subzone codes from the cells.
        phase_ids = list(zone.children.values_list("id", flat=True))
        task_scopes = list(
            ProjectScope.objects.filter(parent_id__in=phase_ids, scope_type=ProjectScope.ScopeType.TASK)
            .select_related("parent").order_by("parent__sort_order", "sort_order")
        )
        task_ids = [t.id for t in task_scopes]
        acts = list(Activity.objects.filter(scope_id__in=task_ids)
                    .values("id", "scope_id", "subzone_code", "subzone_index", "weight", "progress_percent"))

        # Columns: distinct subzone indices (ordered), mapped to their code/name.
        index_name = {}
        for a in acts:
            index_name.setdefault(a["subzone_index"], a["subzone_code"])
        col_order = sorted(index_name)
        col_pos = {idx: i for i, idx in enumerate(col_order)}
        columns = [{"id": str(idx), "name": index_name[idx]} for idx in col_order]

        by_task = {}
        for a in acts:
            by_task.setdefault(a["scope_id"], []).append(a)

        rows = []
        for i, t in enumerate(task_scopes):
            cells = [None] * len(col_order)
            weight = "1"
            for a in by_task.get(t.id, []):
                weight = str(a["weight"])
                ci = col_pos.get(a["subzone_index"])
                if ci is not None:
                    cells[ci] = {"id": str(a["id"]), "progress": str(a["progress_percent"])}
            rows.append({"row_index": i, "name": t.name, "phase": t.parent.name,
                         "weight": weight, "cells": cells})

        return Response({
            "zone": {"id": str(zone.id), "name": zone.name},
            "subzones": columns,
            "rows": rows,
        })


class ScopeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        serializer = ScopeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _validate_parent(project, serializer.validated_data.get("parent"))
        scope = serializer.save(company=request.user.company, project=project)
        return Response(ScopeSerializer(scope).data, status=status.HTTP_201_CREATED)


class ScopeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, project, scope_id):
        try:
            return ProjectScope.objects.get(pk=scope_id, project=project)
        except (ProjectScope.DoesNotExist, ValueError, TypeError):
            raise NotFound("Scope not found.")

    def patch(self, request, project_id, scope_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        scope = self._get(request, project, scope_id)
        serializer = ScopeWriteSerializer(scope, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _validate_parent(project, serializer.validated_data.get("parent"))
        serializer.save()
        return Response(ScopeSerializer(scope).data)

    def delete(self, request, project_id, scope_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(request, project, scope_id).delete()  # cascades children + activities
        return Response(status=status.HTTP_204_NO_CONTENT)


def _validate_scope(project, scope):
    if scope and scope.project_id != project.id:
        raise ValidationError({"scope": "Scope belongs to another project."})


class ActivityListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        serializer = ActivityWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _validate_scope(project, serializer.validated_data.get("scope"))
        activity = serializer.save(company=request.user.company, project=project)
        return Response(ActivitySerializer(activity).data, status=status.HTTP_201_CREATED)


class ActivityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, activity_id):
        try:
            return Activity.objects.get(pk=activity_id, project=project)
        except (Activity.DoesNotExist, ValueError, TypeError):
            raise NotFound("Activity not found.")

    def patch(self, request, project_id, activity_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        activity = self._get(project, activity_id)
        serializer = ActivityWriteSerializer(activity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _validate_scope(project, serializer.validated_data.get("scope"))
        serializer.save()
        return Response(ActivitySerializer(activity).data)

    def delete(self, request, project_id, activity_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(project, activity_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Upload limit (the workbook is large but mostly the skipped P6 sheet).
MAX_IMPORT_BYTES = 40 * 1024 * 1024


class ProjectImportView(APIView):
    """Import an Excel progress-tracker workbook into the project hierarchy.
    Replaces the existing structure."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        if not upload.name.lower().endswith((".xlsx", ".xlsm")):
            raise ValidationError({"file": "Upload an .xlsx or .xlsm file."})
        if upload.size > MAX_IMPORT_BYTES:
            raise ValidationError({"file": "File is too large (max 40 MB)."})
        try:
            result = import_workbook(project, upload)
        except Exception as exc:  # parsing failures shouldn't 500
            raise ValidationError({"file": f"Couldn't read this workbook: {exc}"})
        return Response(result)
