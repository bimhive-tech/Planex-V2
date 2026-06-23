"""Report data assembly — gathers the real project numbers the PDF renders.
We only include data we actually have; missing fields are simply omitted.

Planned %, previous %, duration and delay are *derived* from data we already
hold (project dates + dated snapshots) — no extra manual entry needed."""
import datetime

from apps.projects.models import ProjectImage, ProjectScope
from apps.projects.services import activity_progress_as_of, project_overall_progress

from .models import ReportImage


def _planned_progress(project, as_of):
    """Time-based planned % (0–100): how far along the contract calendar we are.
    Matches the reference, where overdue scopes show planned = 100%."""
    s, f = project.planned_start, project.planned_finish
    if not (s and f and as_of and f > s):
        return None
    frac = (as_of - s).days / (f - s).days
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _duration_for(s, f, revised_finish, as_of):
    """Duration / elapsed / remaining / delay in calendar days for any
    start+finish pair — shared by the project-level and per-zone duration."""
    if not (s and f and f > s):
        return None
    total = (f - s).days
    elapsed = max(0, min(total, (as_of - s).days)) if as_of else 0
    remaining = max(0, total - elapsed)
    if revised_finish and revised_finish > f:
        delay = (revised_finish - f).days
    elif as_of and as_of > f:
        delay = (as_of - f).days
    else:
        delay = 0
    return {"total": total, "elapsed": elapsed, "remaining": remaining, "delay": delay}


def _duration(project, as_of):
    """Contract duration / elapsed / remaining / delay in calendar days."""
    return _duration_for(project.planned_start, project.planned_finish, project.revised_finish, as_of)


def _zone_duration(zone, project, as_of):
    """Same as `_duration`, but using the zone's own dates when it carries
    them — falls back to the project's otherwise (most zones don't, yet)."""
    s = zone.planned_start or project.planned_start
    f = zone.planned_finish or project.planned_finish
    revised = zone.revised_finish or project.revised_finish
    return _duration_for(s, f, revised, as_of)


def _breakdown(project, progress=None):
    """Count activities by progress bucket via a DB aggregate, then — for an as-of
    `progress` map — correct only the handful of overridden activities. Never
    iterate the whole table (these hold tens of thousands of rows)."""
    from django.db.models import Count, Q

    agg = project.activities.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(progress_percent__gte=100)),
        not_started=Count("id", filter=Q(progress_percent__lte=0)),
    )
    total = agg["total"] or 0
    completed = agg["completed"] or 0
    not_started = agg["not_started"] or 0

    if progress:
        def bucket(v):
            return "c" if v >= 100 else ("n" if v <= 0 else "i")

        for aid, cur in project.activities.filter(
            id__in=list(progress.keys())
        ).values_list("id", "progress_percent"):
            cb, nb = bucket(float(cur)), bucket(progress[str(aid)])
            if cb == nb:
                continue
            if cb == "c":
                completed -= 1
            elif cb == "n":
                not_started -= 1
            if nb == "c":
                completed += 1
            elif nb == "n":
                not_started += 1

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


def _zone_rows(project, scope_ids=None, progress=None):
    """Top-level zones with progress rolled up over the *selected* tasks (a zone
    is shown only when it has included tasks). No selection = the whole project.
    `progress` (activity_id->% map) overrides current values for as-of reports."""
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
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        sw[zone] = sw.get(zone, 0.0) + w
        spw[zone] = spw.get(zone, 0.0) + w * prog

    rows = [{"id": z, "name": zone_name[z], "progress": round(spw[z] / sw[z], 1) if sw[z] else 0.0}
            for z in sw]
    rows.sort(key=lambda r: order.get(r["id"], 999))
    return rows


def _scope_planned_progress(scope, project, as_of):
    """Time-based planned % for one scope's own dates, falling back to the
    project's when the scope doesn't carry its own (most don't, yet)."""
    start = scope.planned_start or project.planned_start
    finish = scope.planned_finish or project.planned_finish
    if not (start and finish and as_of and finish > start):
        return None
    frac = (as_of - start).days / (finish - start).days
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _hierarchy_rows(project, scope_ids=None, progress=None, prev_scopes=None, as_of=None):
    """Project -> Zone -> Subzone progress rollup (actual / previous / planned %)
    for the report's nested breakdown table. One level deeper than `_zone_rows`,
    using each scope's own planned dates when set. `prev_scopes` is the previous
    snapshot's full scope_id->% map (blank on snapshots taken before that existed,
    so deeper "previous" values may legitimately be missing)."""
    predicate, _ = _scope_context(project, scope_ids)
    prev_scopes = prev_scopes or {}

    direct_w, direct_pw = {}, {}
    for sid, weight, prog, aid in project.activities.values_list("scope_id", "weight", "progress_percent", "id"):
        if not predicate(sid, aid):
            continue
        sid = str(sid)
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * prog

    scopes = {str(s.id): s for s in project.scopes.all()}
    children = {}
    for s in scopes.values():
        if s.parent_id:
            children.setdefault(str(s.parent_id), []).append(str(s.id))

    weight, pweight = {}, {}

    def agg(sid):
        w, pw = direct_w.get(sid, 0.0), direct_pw.get(sid, 0.0)
        for cid in children.get(sid, []):
            cw, cpw = agg(cid)
            w += cw
            pw += cpw
        weight[sid], pweight[sid] = w, pw
        return w, pw

    def pct(sid):
        w = weight.get(sid, 0.0)
        return round(pweight[sid] / w, 1) if w else None

    zones = sorted(
        (s for s in scopes.values() if s.parent_id is None and s.scope_type == ProjectScope.ScopeType.ZONE),
        key=lambda s: (s.sort_order, s.name),
    )

    rows = []
    for zone in zones:
        zid = str(zone.id)
        agg(zid)
        if not weight.get(zid):
            continue
        sub_rows = []
        for cid in sorted(children.get(zid, []), key=lambda c: (scopes[c].sort_order, scopes[c].name)):
            if not weight.get(cid):
                continue
            child = scopes[cid]
            sub_rows.append({
                "name": child.name, "actual": pct(cid), "previous": prev_scopes.get(cid),
                "planned": _scope_planned_progress(child, project, as_of),
            })
        rows.append({
            "id": zid, "name": zone.name, "actual": pct(zid), "previous": prev_scopes.get(zid),
            "planned": _scope_planned_progress(zone, project, as_of),
            "children": sub_rows,
        })
    return rows


def _discipline_rows(project, scope_ids=None, progress=None):
    """Per-unit (subzone/building) progress split by trade — Concrete /
    Architecture / Electrical / Mechanical — using each activity's *phase*
    discipline tag (a zone-tracker phase is usually one trade's work package,
    and a phase's direct parent is the unit, so no deep tree walk is needed).
    Units with no tagged phases are omitted; untagged work is simply left out
    of the trade columns rather than guessed at."""
    predicate, _ = _scope_context(project, scope_ids)
    disciplines = [d for d in ProjectScope.Discipline.values]

    phases = {
        str(s.id): s for s in project.scopes.filter(
            scope_type=ProjectScope.ScopeType.PHASE).exclude(discipline="")
    }
    if not phases:
        return []

    unit_w, unit_pw = {}, {}
    for sid, weight, prog, aid in project.activities.values_list("scope_id", "weight", "progress_percent", "id"):
        sid = str(sid)
        phase = phases.get(sid)
        if not phase or phase.parent_id is None or not predicate(sid, aid):
            continue
        unit_id = str(phase.parent_id)
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        unit_w.setdefault(unit_id, {}).setdefault(phase.discipline, 0.0)
        unit_pw.setdefault(unit_id, {}).setdefault(phase.discipline, 0.0)
        unit_w[unit_id][phase.discipline] += w
        unit_pw[unit_id][phase.discipline] += w * prog

    units = {str(s.id): s for s in project.scopes.filter(id__in=unit_w.keys())}
    rows = []
    for uid, by_disc in sorted(unit_w.items(), key=lambda kv: (units[kv[0]].sort_order, units[kv[0]].name)):
        row = {"name": units[uid].name}
        for d in disciplines:
            w = by_disc.get(d, 0.0)
            row[d] = round(unit_pw[uid][d] / w, 1) if w else None
        rows.append(row)
    return rows


def _subtree_ids(project, root_id):
    """All scope ids in the subtree rooted at root_id (inclusive)."""
    children = {}
    for sid, pid in project.scopes.values_list("id", "parent_id"):
        if pid:
            children.setdefault(str(pid), []).append(str(sid))
    out, stack = [], [str(root_id)]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(children.get(node, []))
    return out


def _gantt_rows(project, scope_ids=None, progress=None):
    """Zone + direct-child bars for a simple Gantt-style schedule printout.
    Each row's baseline span is its OWN planned_start/planned_finish (set via
    manual entry or the schedule import) — we don't fall back to the project's
    dates the way `_zone_duration` does, since every row would then render an
    identical full-project bar. Rows without both dates are simply omitted.
    No predecessor/float/critical-path computation: the fill just shows the
    row's own rolled-up actual % complete."""
    predicate, _ = _scope_context(project, scope_ids)

    direct_w, direct_pw = {}, {}
    for sid, weight, prog, aid in project.activities.values_list("scope_id", "weight", "progress_percent", "id"):
        if not predicate(sid, aid):
            continue
        sid = str(sid)
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * prog

    scopes = {str(s.id): s for s in project.scopes.all()}
    children = {}
    for s in scopes.values():
        if s.parent_id:
            children.setdefault(str(s.parent_id), []).append(str(s.id))

    weight, pweight = {}, {}

    def agg(sid):
        w, pw = direct_w.get(sid, 0.0), direct_pw.get(sid, 0.0)
        for cid in children.get(sid, []):
            cw, cpw = agg(cid)
            w += cw
            pw += cpw
        weight[sid], pweight[sid] = w, pw
        return w, pw

    def row_for(scope, level):
        sid = str(scope.id)
        agg(sid)
        if not weight.get(sid):
            return None
        if not (scope.planned_start and scope.planned_finish and scope.planned_finish > scope.planned_start):
            return None
        return {
            "name": scope.name, "level": level, "start": scope.planned_start,
            "finish": scope.planned_finish, "revised_finish": scope.revised_finish,
            "progress": round(pweight[sid] / weight[sid], 1),
        }

    zones = sorted(
        (s for s in scopes.values() if s.parent_id is None and s.scope_type == ProjectScope.ScopeType.ZONE),
        key=lambda s: (s.sort_order, s.name),
    )

    rows = []
    for zone in zones:
        zr = row_for(zone, 0)
        if zr:
            rows.append(zr)
        for cid in sorted(children.get(str(zone.id), []), key=lambda c: (scopes[c].sort_order, scopes[c].name)):
            cr = row_for(scopes[cid], 1)
            if cr:
                rows.append(cr)
    return rows


def _area_dashboards(project, hierarchy, as_of):
    """Per-zone dashboard data: its own duration/time-performance (falls back
    to the project's when it has none of its own) and a handful of recent
    progress photos from its subtree. The planned-vs-actual bar chart is drawn
    straight from `hierarchy`'s children, so this only adds what that doesn't."""
    from apps.projects.models import ProgressImage

    zone_ids = [z["id"] for z in hierarchy]
    zones_by_id = {str(s.id): s for s in project.scopes.filter(id__in=zone_ids)}

    out = []
    for z in hierarchy:
        zone = zones_by_id.get(z["id"])
        if not zone:
            continue
        subtree = _subtree_ids(project, z["id"])
        photos = list(
            ProgressImage.objects.filter(entry__project=project, entry__activity__scope_id__in=subtree)
            .order_by("-entry__date", "-created_at")
            .values("image", "caption")[:4]
        )
        out.append({
            "name": z["name"], "actual": z["actual"], "planned": z["planned"],
            "children": z["children"], "duration": _zone_duration(zone, project, as_of),
            "photos": photos,
        })
    return out


def _zone_grids(project, zone_ids, scope_ids=None, progress=None):
    """The schedule-style grid per zone: subzones as columns, tasks (grouped by
    phase) as rows, each cell an activity's progress. Honours the scope selection
    (only included subzones/phases/tasks appear). `progress` (activity_id->% map)
    overrides current cell values for as-of reports."""
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
                val = progress.get(str(a["id"]), float(a["progress_percent"])) if progress is not None else float(a["progress_percent"])
                row["cells"][ci] = round(val, 1)

        rows = [rows_by_index[i] for i in order]
        if columns and rows:
            grids.append({"zone_name": zone.name, "columns": columns, "rows": rows})
    return grids


def build_report_context(report):
    """Assemble the full data dict the PDF generator consumes."""
    project = report.project
    as_of = report.report_date or report.period_finish or datetime.date.today()

    # As-of-date progress: read each activity's % from its latest dated entry on
    # or before the report date. Empty (no entries anywhere) → fast current path.
    progress = activity_progress_as_of(project, as_of) or None

    overall = project_overall_progress(project, progress)
    breakdown = _breakdown(project, progress)

    planned = _planned_progress(project, as_of)
    duration = _duration(project, as_of)

    milestones = list(
        project.milestones.order_by("sort_order", "date").values("title", "date", "status")
    )
    snapshots = list(
        project.snapshots.order_by("date").values("date", "overall_progress", "source", "zones", "scopes")
    )

    # Previous actual = the most recent snapshot strictly before the report date.
    prev_snap = next(
        (s for s in reversed(snapshots) if s["date"] and s["date"] < as_of), None
    )
    prev_zone = {z.get("name"): z.get("progress") for z in (prev_snap["zones"] or [])} if prev_snap else {}
    prev_scopes_map = (prev_snap.get("scopes") or {}) if prev_snap else {}
    prev_overall = float(prev_snap["overall_progress"]) if prev_snap else None

    # Scope-aware: only zones with selected tasks appear; progress rolls up over
    # the selected tasks (empty selection = whole project).
    zones = _zone_rows(project, report.scope_ids, progress)
    for z in zones:
        z["previous"] = prev_zone.get(z["name"])
        z["planned"] = planned  # time-based baseline is project-wide

    # Project -> Zone -> Subzone breakdown (one level deeper than `zones` above).
    hierarchy = _hierarchy_rows(project, report.scope_ids, progress, prev_scopes_map, as_of)
    discipline = _discipline_rows(project, report.scope_ids, progress)
    area_dashboards = _area_dashboards(project, hierarchy, as_of)
    gantt = _gantt_rows(project, report.scope_ids, progress)

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
            "description_html": report.description_html,
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
        "hierarchy": hierarchy,
        "discipline": discipline,
        "area_dashboards": area_dashboards,
        "gantt": gantt,
        "zone_grids": zone_grids,
        # Internal: as-of progress map so the PDF's lazy grid matches the report
        # date (None when the project has no dated entries).
        "_progress": progress,
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
