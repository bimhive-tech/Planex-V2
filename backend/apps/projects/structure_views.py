"""Work-hierarchy API: read the project structure tree, and CRUD scopes/activities.

Routes are nested under a project. Reads need VIEW_PROJECTS; writes need
MANAGE_PROJECTS. Everything is company- and project-scoped (tenant isolation).
"""
import datetime
import logging
from io import BytesIO

from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

logger = logging.getLogger(__name__)

from .access import accessible_scope_ids
from .imports import import_workbook
from .models import Activity, Project, ProjectScope, ScheduleImport
from .serializers import (
    ActivitySerializer,
    ActivityWriteSerializer,
    ScheduleImportSerializer,
    ScopeSerializer,
    ScopeWriteSerializer,
)
from .services import (
    breakdown_from_map,
    latest_schedule_import,
    progress_series,
    project_overall_progress,
    scope_progress_map,
    view_progress_map,
)


def _view_map(request, project):
    """Build the Schedule view-mode override map from ?mode & ?as_of query params.
    Returns None for the default 'current' view (callers use live values)."""
    mode = request.query_params.get("mode", "current")
    raw = request.query_params.get("as_of")
    as_of = None
    if raw:
        try:
            as_of = datetime.date.fromisoformat(raw)
        except (ValueError, TypeError):
            as_of = None
    if mode in ("asof", "month") and as_of:
        return view_progress_map(project, mode, as_of)
    return None


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
    """Base project access — gates the scope/activity NAME tree (used broadly by
    the Report Builder's and Team's scope pickers, not just the Schedule tab)."""
    perms = request.user.effective_permissions()
    if Permission.VIEW_PROJECTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
        raise PermissionDenied("You don't have permission to view this.")


def _require_view_schedule(request):
    """Gates the Schedule tab's actual progress data (structure/grid/snapshots)."""
    perms = request.user.effective_permissions()
    if Permission.VIEW_SCHEDULE.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
        raise PermissionDenied("You don't have permission to view the schedule.")


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
        _require_view_schedule(request)
        accessible = accessible_scope_ids(project, request.user)

        # ?import_id=<uuid> views an older import's own full state — omitted
        # (the common case) always resolves to the latest, so the tab shows
        # current data by default and only shows history when explicitly
        # asked (2026-08-30: "we will always show the latest data unless I
        # filter to show a later month"). See ScheduleImport's own docstring.
        import_id = request.query_params.get("import_id")
        if import_id:
            try:
                schedule_import = ScheduleImport.objects.get(pk=import_id, project=project)
            except (ScheduleImport.DoesNotExist, ValueError, TypeError):
                raise NotFound("Import not found.")
        else:
            schedule_import = latest_schedule_import(project)

        scopes_qs = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
        if accessible is not None:
            scopes_qs = scopes_qs.filter(id__in=accessible)
        activities_qs = (
            project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
        )
        counts = {
            str(r["scope_id"]): r["n"]
            for r in activities_qs.values("scope_id").annotate(n=Count("id"))
            if accessible is None or r["scope_id"] in accessible
        }
        # Optional as-of / month-delta view (?mode=asof|month&as_of=YYYY-MM-DD)
        # — a different axis (dated progress-entry readings against the same
        # current schedule), independent of which import batch is shown.
        value_map = _view_map(request, project)
        if value_map is None:
            from django.db.models import Q
            agg = activities_qs.aggregate(
                total=Count("id"),
                completed=Count("id", filter=Q(progress_percent__gte=100)),
                not_started=Count("id", filter=Q(progress_percent__lte=0)),
            )
            total = agg["total"]
            breakdown = {
                "total": total, "completed": agg["completed"], "not_started": agg["not_started"],
                "in_progress": total - agg["completed"] - agg["not_started"],
            }
        else:
            breakdown = breakdown_from_map(project, value_map, schedule_import)
            total = breakdown["total"]
        return Response({
            "overall_progress": project_overall_progress(project, value_map, schedule_import),
            "scope_progress": scope_progress_map(project, value_map, schedule_import),
            "scopes": ScopeSerializer(scopes_qs, many=True).data,
            "scope_activity_counts": counts,
            "activity_count": total,
            "progress_breakdown": breakdown,
            "schedule_import_id": str(schedule_import.id) if schedule_import else None,
            "schedule_import_date": schedule_import.date.isoformat() if schedule_import else None,
        })


class ScopeTreeView(APIView):
    """Lazy scope tree for the report's scope picker: children of `parent`
    (top-level zones when absent), each tagged with whether it can expand."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        parent = request.query_params.get("parent")
        # Top-level (no parent given) is scoped to the current import batch —
        # otherwise every past import's zones would pile up as duplicate
        # top-level picker options. A `parent` id is always already
        # batch-scoped by construction (it came from a previous call into
        # this same view), so no further filtering is needed walking down.
        if not parent:
            schedule_import = latest_schedule_import(project)
            qs = project.scopes.filter(parent__isnull=True, schedule_import=schedule_import) if schedule_import \
                else project.scopes.filter(parent__isnull=True)
        else:
            qs = project.scopes.filter(parent_id=parent)
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
        data = ActivitySerializer(acts, many=True).data
        value_map = _view_map(request, project)
        if value_map is not None:
            for d in data:
                v = value_map.get(str(d["id"]))
                if v is not None:  # asof: sparse (missing → keep current); month: complete
                    d["progress_percent"] = str(round(v, 2))
        return Response(data)


class ProjectZoneGridView(APIView):
    """GET the Excel-style matrix for one zone: subzones (columns) x tasks (rows),
    each cell an activity's progress."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, zone_id):
        project = _project(request, project_id)
        _require_view_schedule(request)
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
        value_map = _view_map(request, project)  # as-of / month-delta override

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
                prog = a["progress_percent"]
                if value_map is not None:
                    v = value_map.get(str(a["id"]))
                    if v is not None:
                        prog = round(v, 2)
                row["cells"][ci] = {"id": str(a["id"]), "progress": str(prog)}

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
        # A hand-added scope belongs to whichever import batch is current
        # right now — same "always current" default a hand-added activity
        # gets right below, so it doesn't vanish from the live view the
        # moment schedule_import-based filtering (added alongside this
        # feature) starts applying to `project.scopes`/`project.activities`.
        scope = serializer.save(company=request.user.company, project=project,
                                schedule_import=latest_schedule_import(project))
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
        activity = serializer.save(company=request.user.company, project=project,
                                   schedule_import=latest_schedule_import(project))
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

        # The date this schedule DATA is as of — not necessarily today.
        # Defaults (inside import_workbook) to a date parsed from the
        # filename, then to today, when the caller doesn't choose one.
        snapshot_date = None
        raw_date = request.data.get("date")
        if raw_date:
            import datetime as _dt
            try:
                snapshot_date = _dt.date.fromisoformat(raw_date)
            except ValueError:
                raise ValidationError({"date": "Use YYYY-MM-DD."})

        # Read the bytes once: import parses from a copy, and the same bytes are
        # retained verbatim for the P6 export (so neither read disturbs the other).
        raw = upload.read()
        try:
            result = import_workbook(project, BytesIO(raw), source=upload.name, snapshot_date=snapshot_date)
        except Exception as exc:  # parsing failures shouldn't 500
            raise ValidationError({"file": f"Couldn't read this workbook: {exc}"})

        # Retain the original workbook so the P6 export can be returned with only
        # its progress column refreshed (see exports.refresh_source_workbook) —
        # always the LATEST import's file, refreshed each time.
        # Non-fatal: the structure import already succeeded — but log failures
        # (don't swallow them) so a misconfigured store is visible, not silent.
        try:
            if project.source_workbook:
                project.source_workbook.delete(save=False)
            project.source_workbook.save(upload.name, ContentFile(raw), save=True)
        except Exception:
            logger.exception("Failed to retain source workbook for project %s", project.id)

        # Also retain THIS import's own copy, keyed to its own batch — unlike
        # source_workbook above (always overwritten), every past import's
        # workbook stays downloadable. Same non-fatal logging treatment.
        schedule_import_id = result.get("schedule_import_id")
        if schedule_import_id:
            try:
                from .models import ScheduleImport

                batch = ScheduleImport.objects.get(id=schedule_import_id)
                batch.file.save(upload.name, ContentFile(raw), save=True)
            except Exception:
                logger.exception("Failed to retain schedule-import workbook %s", schedule_import_id)

        return Response(result)


class ScheduleImportListView(APIView):
    """List every retained schedule-import batch for a project, newest first —
    the picker's data source (see ScheduleImport's own docstring). Small list
    (one row per import, not per activity), so no pagination."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view_schedule(request)
        latest = latest_schedule_import(project)
        imports = project.schedule_imports.all()
        data = ScheduleImportSerializer(
            imports, many=True, context={"latest_id": latest.id if latest else None}).data
        return Response(data)


class ScheduleImportFileView(APIView):
    """Stream one retained import's own workbook — same private, tenant-scoped
    pattern as ProjectImageFileView (apps/projects/image_views.py)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, import_id):
        import mimetypes

        from django.http import FileResponse, Http404

        project = _project(request, project_id)
        _require_view_schedule(request)
        try:
            batch = project.schedule_imports.get(pk=import_id)
        except (ScheduleImport.DoesNotExist, ValueError, TypeError):
            raise NotFound("Import not found.")
        if not batch.file:
            raise Http404
        content_type = mimetypes.guess_type(batch.file.name)[0] or "application/octet-stream"
        return FileResponse(batch.file.open("rb"), content_type=content_type, filename=batch.source or "schedule.xlsx")


class ProjectSnapshotsView(APIView):
    """GET the project's actual-vs-planned progress over time — computed live
    from current data (dated Update readings + import baselines + a live today
    point), so it reflects any progress or date change, not just imports."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        return Response(progress_series(project))
