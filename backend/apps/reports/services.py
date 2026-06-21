"""Report data assembly — gathers the real project numbers the PDF renders.
We only include data we actually have; missing fields are simply omitted.

Planned %, previous %, duration and delay are *derived* from data we already
hold (project dates + dated snapshots) — no extra manual entry needed."""
import datetime

from apps.projects.models import ProjectImage, ProjectScope
from apps.projects.services import project_overall_progress, scope_progress_map

from .models import ReportImage


def _planned_progress(project, as_of):
    """Time-based planned % (0–100): how far along the contract calendar we are.
    Matches the reference, where overdue scopes show planned = 100%."""
    s, f = project.planned_start, project.planned_finish
    if not (s and f and as_of and f > s):
        return None
    frac = (as_of - s).days / (f - s).days
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _duration(project, as_of):
    """Contract duration / elapsed / remaining / delay in calendar days."""
    s, f = project.planned_start, project.planned_finish
    if not (s and f and f > s):
        return None
    total = (f - s).days
    elapsed = max(0, min(total, (as_of - s).days)) if as_of else 0
    remaining = max(0, total - elapsed)
    if project.revised_finish and project.revised_finish > f:
        delay = (project.revised_finish - f).days
    elif as_of and as_of > f:
        delay = (as_of - f).days
    else:
        delay = 0
    return {"total": total, "elapsed": elapsed, "remaining": remaining, "delay": delay}


def _breakdown(project):
    """Count activities by progress bucket — in the DB, not Python (these tables
    hold tens of thousands of rows)."""
    from django.db.models import Count, Q

    agg = project.activities.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(progress_percent__gte=100)),
        not_started=Count("id", filter=Q(progress_percent__lte=0)),
    )
    total = agg["total"] or 0
    completed = agg["completed"] or 0
    not_started = agg["not_started"] or 0
    return {
        "total": total,
        "completed": completed,
        "in_progress": max(0, total - completed - not_started),
        "not_started": not_started,
    }


def _scope_context(project, scope_ids):
    """Resolve the report's scope selection into (predicate, scope_to_zone).

    `predicate(scope_id, activity_id)` is True when an activity is in the export:
    its scope (or an ancestor scope) was ticked, or the task itself was ticked.
    An empty selection includes everything. `scope_to_zone` maps any scope to its
    top-level zone, so we can roll progress up per zone over the included tasks."""
    rows = list(project.scopes.values_list("id", "parent_id"))
    parent = {str(sid): (str(pid) if pid else None) for sid, pid in rows}

    scope_to_zone, children = {}, {}
    for sid, pid in rows:
        if pid:
            children.setdefault(str(pid), []).append(str(sid))
    for sid in parent:
        cur, chain = sid, []
        while parent.get(cur):
            chain.append(cur)
            cur = parent[cur]
        for s in chain:
            scope_to_zone[s] = cur
        scope_to_zone[cur] = cur

    sel = {str(s) for s in (scope_ids or [])}
    if not sel:
        return (lambda sc, ac: True), scope_to_zone

    selected_scopes = sel & set(parent)
    selected_tasks = sel - selected_scopes
    covered, stack = set(), list(selected_scopes)
    while stack:
        node = stack.pop()
        if node in covered:
            continue
        covered.add(node)
        stack.extend(children.get(node, []))

    def predicate(scope_id, activity_id):
        return str(scope_id) in covered or str(activity_id) in selected_tasks

    return predicate, scope_to_zone


def _zone_rows(project, scope_ids=None):
    """Top-level zones with progress rolled up over the *selected* tasks (a zone
    is shown only when it has included tasks). No selection = the whole project."""
    predicate, scope_to_zone = _scope_context(project, scope_ids)
    zones = list(
        ProjectScope.objects.filter(
            project=project, parent__isnull=True, scope_type=ProjectScope.ScopeType.ZONE
        ).order_by("sort_order", "name").values_list("id", "name")
    )
    order = {str(z): i for i, (z, _) in enumerate(zones)}
    zone_name = {str(z): name for z, name in zones}

    sw, spw = {}, {}
    for sid, weight, prog, aid in project.activities.values_list("scope_id", "weight", "progress_percent", "id"):
        if not predicate(sid, aid):
            continue
        zone = scope_to_zone.get(str(sid))
        if zone not in zone_name:
            continue
        w, prog = float(weight), float(prog)
        sw[zone] = sw.get(zone, 0.0) + w
        spw[zone] = spw.get(zone, 0.0) + w * prog

    rows = [{"id": z, "name": zone_name[z], "progress": round(spw[z] / sw[z], 1) if sw[z] else 0.0}
            for z in sw]
    rows.sort(key=lambda r: order.get(r["id"], 999))
    return rows


def _zone_grids(project, zone_ids, scope_ids=None):
    """The schedule-style grid per zone: subzones as columns, tasks (grouped by
    phase) as rows, each cell an activity's progress. Honours the scope selection
    (only included subzones/phases/tasks appear)."""
    from apps.projects.models import Activity, ProjectScope

    predicate, _ = _scope_context(project, scope_ids)
    grids = []
    zones = {str(z.id): z for z in ProjectScope.objects.filter(project=project, id__in=zone_ids)}
    for zid in zone_ids:
        zone = zones.get(zid)
        if zone is None:
            continue
        subzone_ids = list(ProjectScope.objects.filter(parent_id=zone.id).values_list("id", flat=True))
        phase_ids = list(ProjectScope.objects.filter(
            parent_id__in=subzone_ids, scope_type=ProjectScope.ScopeType.PHASE
        ).values_list("id", flat=True))
        acts = [a for a in Activity.objects.filter(scope_id__in=phase_ids).values(
            "id", "scope_id", "name", "phase_name", "progress_percent", "row_index", "subzone_index", "subzone_code")
            if predicate(a["scope_id"], a["id"])]

        index_name = {}
        for a in acts:
            index_name.setdefault(a["subzone_index"], a["subzone_code"])
        col_order = sorted(index_name)
        col_pos = {idx: i for i, idx in enumerate(col_order)}
        columns = [index_name[idx] or "" for idx in col_order]

        rows_by_index, order = {}, []
        for a in sorted(acts, key=lambda x: (x["row_index"], x["name"])):
            ri = a["row_index"]
            row = rows_by_index.get(ri)
            if row is None:
                row = {"name": a["name"], "phase": a["phase_name"] or "", "cells": [None] * len(col_order)}
                rows_by_index[ri] = row
                order.append(ri)
            ci = col_pos.get(a["subzone_index"])
            if ci is not None:
                row["cells"][ci] = round(float(a["progress_percent"]), 1)

        rows = [rows_by_index[i] for i in order]
        if columns and rows:
            grids.append({"zone_name": zone.name, "columns": columns, "rows": rows})
    return grids


def build_report_context(report):
    """Assemble the full data dict the PDF generator consumes."""
    project = report.project
    overall = project_overall_progress(project)
    breakdown = _breakdown(project)
    as_of = report.report_date or report.period_finish or datetime.date.today()

    planned = _planned_progress(project, as_of)
    duration = _duration(project, as_of)

    milestones = list(
        project.milestones.order_by("sort_order", "date").values("title", "date", "status")
    )
    snapshots = list(
        project.snapshots.order_by("date").values("date", "overall_progress", "source", "zones")
    )

    # Previous actual = the most recent snapshot strictly before the report date.
    prev_snap = next(
        (s for s in reversed(snapshots) if s["date"] and s["date"] < as_of), None
    )
    prev_zone = {z.get("name"): z.get("progress") for z in (prev_snap["zones"] or [])} if prev_snap else {}
    prev_overall = float(prev_snap["overall_progress"]) if prev_snap else None

    # Scope-aware: only zones with selected tasks appear; progress rolls up over
    # the selected tasks (empty selection = whole project).
    zones = _zone_rows(project, report.scope_ids)
    for z in zones:
        z["previous"] = prev_zone.get(z["name"])
        z["planned"] = planned  # time-based baseline is project-wide

    # Grids are heavy (tens of thousands of cells); the PDF computes them lazily
    # only when the detailed-progress section is enabled.
    zone_grids = []

    delays = list(
        project.delays.order_by("sort_order", "-date").values("title", "description", "impact_days", "status", "date")
    )

    # S-curve series: actual (from snapshots) vs planned at each snapshot date.
    scurve = [
        {
            "date": s["date"],
            "actual": float(s["overall_progress"]),
            "planned": _planned_progress(project, s["date"]),
        }
        for s in snapshots if s["date"]
    ]
    # Logos stay on the project (constant branding); the cover/photos/attachments
    # are per-report content that overrides any project-level fallback.
    proj_images = list(
        project.images.order_by("image_type", "sort_order", "created_at")
        .values("image_type", "caption", "image")
    )
    rep_images = list(
        report.images.order_by("kind", "sort_order", "created_at").values("kind", "caption", "image")
    )

    def proj(kind):
        return next((i for i in proj_images if i["image_type"] == kind), None)

    def rep(kind):
        return [i for i in rep_images if i["kind"] == kind]

    rep_cover = rep(ReportImage.Kind.COVER)
    rep_photos = rep(ReportImage.Kind.PROGRESS)
    attachments = rep(ReportImage.Kind.ATTACHMENT)

    return {
        "report": {
            "title": report.title,
            "number": report.report_number,
            "date": report.report_date,
            "period_start": report.period_start,
            "period_finish": report.period_finish,
            "status": report.get_status_display(),
        },
        "project": {
            "name": project.name,
            "code": project.code,
            "type": project.get_project_type_display(),
            "location": project.location,
            # Report narrative wins; fall back to the project's description.
            "description": report.description or project.description,
            "client": project.client_name,
            "consultant": project.consultant_name,
            "contractor": project.contractor_name,
            "planned_start": project.planned_start,
            "planned_finish": project.planned_finish,
            "revised_finish": project.revised_finish,
            "size_sqm": project.size_sqm,
            "budget": project.budget,
            "currency": project.currency,
            "notes": project.notes,
        },
        "overall": overall,
        "planned": planned,
        "previous_overall": prev_overall,
        "duration": duration,
        "breakdown": breakdown,
        "zones": zones,
        "zone_grids": zone_grids,
        "delays": delays,
        "scurve": scurve,
        "milestones": milestones,
        "snapshots": snapshots,
        "logos": {
            "left": proj(ProjectImage.ImageType.LOGO_LEFT),
            "right": proj(ProjectImage.ImageType.LOGO_RIGHT),
            "cover": (rep_cover[0] if rep_cover else proj(ProjectImage.ImageType.COVER)),
        },
        "photos": rep_photos or [i for i in proj_images if i["image_type"] == ProjectImage.ImageType.SITE_PHOTO],
        "attachments": attachments,
    }
