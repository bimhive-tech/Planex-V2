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

from .access import accessible_scope_ids
from .imports import import_schedule, import_workbook
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


from django.db.models import Count


class ProjectStructureView(APIView):
    """GET the scope tree + rolled-up progress + a per-scope activity count.
    Activities themselves are loaded lazily per scope (a zone tracker has tens of
    thousands), via ScopeActivitiesView."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        accessible = accessible_scope_ids(project, request.user)
        scopes_qs = project.scopes.all()
        if accessible is not None:
            scopes_qs = scopes_qs.filter(id__in=accessible)
        counts = {
            str(r["scope_id"]): r["n"]
            for r in project.activities.values("scope_id").annotate(n=Count("id"))
            if accessible is None or r["scope_id"] in accessible
        }
        from django.db.models import Q
        agg = project.activities.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(progress_percent__gte=100)),
            not_started=Count("id", filter=Q(progress_percent__lte=0)),
        )
        total = agg["total"]
        return Response({
            "overall_progress": project_overall_progress(project),
            "scope_progress": scope_progress_map(project),
            "scopes": ScopeSerializer(scopes_qs, many=True).data,
            "scope_activity_counts": counts,
            "activity_count": total,
            "progress_breakdown": {
                "total": total, "completed": agg["completed"], "not_started": agg["not_started"],
                "in_progress": total - agg["completed"] - agg["not_started"],
            },
        })


class ScopeTreeView(APIView):
    """Lazy scope tree for the report's scope picker: children of `parent`
    (top-level zones when absent), each tagged with whether it can expand."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        parent = request.query_params.get("parent")
        qs = project.scopes.filter(parent__isnull=True) if not parent else project.scopes.filter(parent_id=parent)
        children = list(qs.order_by("sort_order", "name").values("id", "name", "scope_type"))
        ids = [c["id"] for c in children]
        has_sub = set(ProjectScope.objects.filter(parent_id__in=ids).values_list("parent_id", flat=True))
        has_acts = set(Activity.objects.filter(scope_id__in=ids).values_list("scope_id", flat=True))
        return Response([
            {"id": str(c["id"]), "name": c["name"], "type": c["scope_type"],
             "has_children": c["id"] in has_sub or c["id"] in has_acts}
            for c in children
        ])


class ScopeActivitiesView(APIView):
    """GET the activities directly under one scope (lazy tree expansion)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, scope_id):
        project = _project(request, project_id)
        _require_view(request)
        try:
            scope = ProjectScope.objects.get(pk=scope_id, project=project)
        except (ProjectScope.DoesNotExist, ValueError, TypeError):
            raise NotFound("Scope not found.")
        accessible = accessible_scope_ids(project, request.user)
        if accessible is not None and scope.id not in accessible:
            raise PermissionDenied("You don't have access to this part of the project.")
        acts = scope.activities.order_by("row_index", "name")
        return Response(ActivitySerializer(acts, many=True).data)


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
        accessible = accessible_scope_ids(project, request.user)
        if accessible is not None and zone.id not in accessible:
            raise PermissionDenied("You don't have access to this zone.")

        # Tree is Zone -> Subzone -> Phase -> Activity(cell). Columns are subzones
        # (subzone_index), rows are tasks (row_index); cells come from the activities
        # under this zone's phase scopes.
        subzone_ids = list(zone.children.values_list("id", flat=True))
        phase_ids = list(ProjectScope.objects.filter(
            parent_id__in=subzone_ids, scope_type=ProjectScope.ScopeType.PHASE
        ).values_list("id", flat=True))
        acts = list(Activity.objects.filter(scope_id__in=phase_ids).values(
            "id", "name", "phase_name", "weight", "progress_percent",
            "row_index", "subzone_index", "subzone_code"))

        index_name = {}
        for a in acts:
            index_name.setdefault(a["subzone_index"], a["subzone_code"])
        col_order = sorted(index_name)
        col_pos = {idx: i for i, idx in enumerate(col_order)}
        columns = [{"id": str(idx), "name": index_name[idx]} for idx in col_order]

        rows_by_index, order = {}, []
        for a in sorted(acts, key=lambda x: (x["row_index"], x["name"])):
            ri = a["row_index"]
            row = rows_by_index.get(ri)
            if row is None:
                row = {"row_index": ri, "name": a["name"], "phase": a["phase_name"],
                       "weight": str(a["weight"]), "cells": [None] * len(col_order)}
                rows_by_index[ri] = row
                order.append(ri)
            ci = col_pos.get(a["subzone_index"])
            if ci is not None:
                row["cells"][ci] = {"id": str(a["id"]), "progress": str(a["progress_percent"])}

        return Response({
            "zone": {"id": str(zone.id), "name": zone.name},
            "subzones": columns,
            "rows": [rows_by_index[i] for i in order],
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
            result = import_workbook(project, upload, source=upload.name)
        except Exception as exc:  # parsing failures shouldn't 500
            raise ValidationError({"file": f"Couldn't read this workbook: {exc}"})

        # Retain the original workbook so the P6 export can be returned with only
        # its progress column refreshed (see exports.build_p6_export).
        try:
            upload.seek(0)
            if project.source_workbook:
                project.source_workbook.delete(save=False)
            project.source_workbook.save(upload.name, upload, save=True)
        except Exception:  # keeping the source is best-effort; the import already succeeded
            pass

        return Response(result)


class ProjectScheduleImportView(APIView):
    """Import a flat schedule export (Activity Name + Start + Finish columns —
    the shape Primavera P6 exports to Excel) and set matching scopes' planned
    dates. Only ever sets dates on existing scopes; never touches structure."""

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
            result = import_schedule(project, upload)
        except Exception as exc:  # parsing failures shouldn't 500
            raise ValidationError({"file": f"Couldn't read this workbook: {exc}"})
        return Response(result)


class ProjectSnapshotsView(APIView):
    """GET the project's dated progress snapshots (one per import) for the timeline."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        snaps = project.snapshots.order_by("date").values(
            "date", "overall_progress", "breakdown", "zones", "source")
        return Response([
            {"date": s["date"], "overall_progress": float(s["overall_progress"]),
             "breakdown": s["breakdown"], "zones": s["zones"], "source": s["source"]}
            for s in snaps
        ])
