"""Report data assembly — gathers the real project numbers the PDF renders.
We only include data we actually have; missing fields are simply omitted.

Planned %, previous %, duration and delay are *derived* from data we already
hold (project dates + dated snapshots) — no extra manual entry needed."""
import copy
import datetime
import re

from django.db.models import Sum

from apps.projects.models import ProjectImage, ProjectScope, Submittal, Variation
from apps.projects.services import (
    activity_progress_as_of, latest_schedule_import, project_overall_progress, scope_planned_map,
)

from .models import ReportImage


def _planned_progress(project, as_of, use_imported=False):
    """Time-based planned % (0–100): how far along the contract calendar we are.
    Matches the reference, where overdue scopes show planned = 100%.

    `use_imported=True` prefers the project's own stated Schedule % Complete
    when a real P6 import provided one — the same reasoning as
    project_overall_progress's actual-progress override, and gated the same
    way (only the report's single "current" figure, never a per-date series:
    the S-curve calls this once per historical snapshot date and must always
    compute live, or every point would show today's one imported number)."""
    if use_imported and project.imported_planned_progress_percent is not None:
        return float(project.imported_planned_progress_percent)
    s, f = project.planned_start, project.planned_finish
    if not (s and f and as_of and f > s):
        return None
    frac = (as_of - s).days / (f - s).days
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _duration_for(s, f, revised_finish, as_of, planned_pct=None, actual_pct=None):
    """Duration / elapsed / remaining / delay in calendar days for any
    start+finish pair — shared by the project-level and per-zone duration.

    Delay, in priority order: (1) an explicit `revised_finish` — a
    human-recorded EOT, trusted outright; (2) `as_of` already past `f` —
    genuinely, officially overdue; (3) `planned_pct`/`actual_pct`, when
    given — a pace-based estimate (the gap between them, translated into
    days via `total`) for a scope that hasn't formally missed its deadline
    yet but is already running behind. Without (3), a scope reports exactly
    0 delay for its *entire* run right up until its own deadline arrives, no
    matter how far behind pace it's actually running — the bug this
    replaced (found 2026-08-25 via the Critical Path Delays table always
    showing 0, then also found reproducing on the per-zone duration widget,
    the same root cause `_zone_duration` docstring already flagged)."""
    if not (s and f and f > s):
        return None
    total = (f - s).days
    elapsed = max(0, min(total, (as_of - s).days)) if as_of else 0
    remaining = max(0, total - elapsed)
    if revised_finish and revised_finish > f:
        delay = (revised_finish - f).days
    elif as_of and as_of > f:
        delay = (as_of - f).days
    elif planned_pct is not None and actual_pct is not None and planned_pct > actual_pct:
        delay = round((planned_pct - actual_pct) / 100 * total)
    else:
        delay = 0
    return {"total": total, "elapsed": elapsed, "remaining": remaining, "delay": delay}


def _duration(project, as_of):
    """Contract duration / elapsed / remaining / delay in calendar days."""
    return _duration_for(project.planned_start, project.planned_finish, project.revised_finish, as_of)


def _zone_duration(zone, project, as_of, planned_pct=None, actual_pct=None):
    """Same as `_duration`, but using the zone's own dates when it carries
    them — falls back to the project's otherwise (most zones don't, yet).
    `planned_pct`/`actual_pct` (the same time-based-planned vs. real-actual
    percentages `_hierarchy_rows` already computes for this zone) feed
    `_duration_for`'s pace-based delay estimate — pass them whenever the
    caller already has them (see `_area_dashboards`/`_critical_path_rows`)."""
    s = zone.planned_start or project.planned_start
    f = zone.planned_finish or project.planned_finish
    revised = zone.revised_finish or project.revised_finish
    return _duration_for(s, f, revised, as_of, planned_pct, actual_pct)


def _breakdown(project, progress=None, schedule_import=None):
    """Count activities by progress bucket via a DB aggregate, then — for an as-of
    `progress` map — correct only the handful of overridden activities. Never
    iterate the whole table (these hold tens of thousands of rows).
    `schedule_import` pins the batch — see build_report_context's own
    resolution of it; every caller here passes the same one."""
    from django.db.models import Count, Q

    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    agg = activities.aggregate(
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

        for aid, cur in activities.filter(
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


def _scope_context(project, scope_ids, schedule_import=None):
    """Resolve the report's scope selection into (predicate, scope_to_zone).

    `predicate(scope_id, activity_id)` is True when an activity is in the export:
    its scope (or an ancestor scope) was ticked, or the task itself was ticked.
    An empty selection includes everything. `scope_to_zone` maps any scope to its
    zone, so we can roll progress up per zone over the included tasks — the
    nearest ZONE-typed ancestor (or itself), NOT simply the top of the tree:
    a P6 import can nest Zone under Stage (`ScopeType.STAGE` is explicitly "a
    top-level grouping above zones"), so walking straight to the root would
    roll everything up to the Stage id instead, which `_zone_rows`'s
    `scope_type=ZONE` query never matches — every zone-scoped section
    (progress-by-zone, hierarchy, discipline, gantt, the detailed grid) would
    render silently empty for any project using that hierarchy shape.

    `schedule_import` pins the batch these scopes/activities are read from —
    see build_report_context's own resolution of it."""
    scopes = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    rows = list(scopes.values_list("id", "parent_id", "scope_type"))
    parent = {str(sid): (str(pid) if pid else None) for sid, pid, _st in rows}
    scope_type = {str(sid): st for sid, _pid, st in rows}

    scope_to_zone, children = {}, {}
    for sid, pid, _st in rows:
        if pid:
            children.setdefault(str(pid), []).append(str(sid))
    zone_type = ProjectScope.ScopeType.ZONE
    for sid in parent:
        cur = sid
        while cur is not None and scope_type.get(cur) != zone_type:
            cur = parent.get(cur)
        # No zone-typed ancestor at all (an older/flatter import where zone
        # genuinely is the root, or a scope above the first zone) — fall
        # back to the top of the chain, same as before.
        if cur is None:
            cur = sid
            while parent.get(cur):
                cur = parent[cur]
        scope_to_zone[sid] = cur

    sel = {str(s) for s in (scope_ids or [])}
    if not sel:
        return (lambda sc, ac: True), scope_to_zone

    selected_scopes = sel & set(parent)
    remaining = sel - selected_scopes
    # Whatever's left of the selection is assumed to be individual activity
    # ids (the scope picker allows selecting down to a single task) — but a
    # *stale* scope_ids list (every id left over from a schedule_import batch
    # that's no longer current — every import creates fresh ProjectScope/
    # Activity UUIDs rather than reusing the previous batch's, see
    # ScheduleImport's own docstring) would otherwise match nothing here either,
    # silently excluding every real scope and rendering the whole report's
    # zone-scoped data empty with no error. Only trust `remaining` as real
    # task ids once at least one of them is confirmed to still exist.
    selected_tasks = set()
    if remaining:
        activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
        real_tasks = {str(a) for a in activities.filter(id__in=remaining).values_list("id", flat=True)}
        selected_tasks = remaining & real_tasks

    if not selected_scopes and not selected_tasks:
        # The entire saved selection is stale — fall back to "everything"
        # selected (same as an empty scope_ids) instead of a silently empty report.
        return (lambda sc, ac: True), scope_to_zone

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


def _zone_area_label(zone_name: str, area_name: str) -> str:
    """A compact "which zone, which building" label: "Z(A)" + "Building 6" -> "A6".

    The stage dashboard's bar chart carries every building in the stage, and the
    same building number genuinely recurs under different zones ("Building 6"
    exists under both Z(A) and Z(E)), so the bare area name names two different
    bars. The client's own dashboard labels these "(A6)", "(E7)", "(C30)" — the
    zone's letter followed by the building's number — which is both unambiguous
    and far shorter than "Z(A) - Building 6", and short labels are what let a
    74-bar chart print every one of them (2026-09-03).

    Deliberately tolerant of other naming schemes: the zone token is whatever
    sits inside its trailing brackets (or the name itself), the area token is its
    trailing number (or the name itself), and anything that doesn't reduce to a
    short pair falls back to "zone - area" rather than inventing a format.
    """
    zone_name, area_name = (zone_name or "").strip(), (area_name or "").strip()
    if not zone_name:
        return area_name
    if not area_name:
        return zone_name

    bracketed = re.search(r"[(\[]([^)\]]+)[)\]]\s*$", zone_name)
    zone_token = (bracketed.group(1) if bracketed else zone_name).strip()

    trailing_number = re.search(r"(\d+)\s*$", area_name)
    area_token = trailing_number.group(1) if trailing_number else area_name.strip()

    joined = f"{zone_token}{area_token}"
    # Only worth joining when the result still reads as one short token; a zone
    # called "Northern Precinct" would otherwise produce "Northern Precinct6".
    if len(zone_token) <= 3 and trailing_number and len(joined) <= 8:
        return joined
    return f"{zone_token} - {area_token}"


def _disambiguated_names(scopes):
    """`scopes`: an iterable of (id, name, parent_id). Returns {str(id): name} —
    a name shared by more than one scope in the set (a P6 import can genuinely
    have several zones all called "Z(A)" under different stages/buildings —
    see this function's callers) gets prefixed with its own parent's name
    ("Stage 1 - Z(A)") so a reader can tell them apart in a compact chart/table
    view; a name that's already unique on its own is left exactly as-is, so
    the common case (no collision) never grows a label unnecessarily."""
    from collections import Counter
    scopes = list(scopes)
    counts = Counter(name for _, name, _ in scopes)
    parent_ids = {pid for _, _, pid in scopes if pid}
    parent_names = (
        dict(ProjectScope.objects.filter(id__in=parent_ids).values_list("id", "name"))
        if parent_ids else {}
    )
    result = {}
    for sid, name, pid in scopes:
        parent_name = parent_names.get(pid) if pid else None
        result[str(sid)] = f"{parent_name} - {name}" if counts[name] > 1 and parent_name else name
    return result


def _zone_rows(project, scope_ids=None, progress=None, schedule_import=None):
    """Zones with progress rolled up over the *selected* tasks (a zone is shown
    only when it has included tasks). No selection = the whole project.
    `progress` (activity_id->% map) overrides current values for as-of reports.
    `schedule_import` pins the batch — see build_report_context's own
    resolution of it.

    Matches every ZONE-typed scope regardless of parent — NOT just top-level
    ones: a P6 import can nest Zone under Stage (see `_scope_context`), so a
    `parent__isnull=True` filter here would exclude every real zone in that
    shape even though `scope_to_zone` correctly resolves activities to them."""
    predicate, scope_to_zone = _scope_context(project, scope_ids, schedule_import)
    zones = list(
        ProjectScope.objects.filter(
            project=project, scope_type=ProjectScope.ScopeType.ZONE, schedule_import=schedule_import
        ).order_by("sort_order", "name").values_list("id", "name", "parent_id")
    )
    order = {str(z): i for i, (z, _, _) in enumerate(zones)}
    zone_name = _disambiguated_names(zones)

    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    sw, spw = {}, {}
    for sid, weight, prog, aid in activities.values_list("scope_id", "weight", "progress_percent", "id"):
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


def _scope_planned_progress(scope, project, as_of, planned_map=None):
    """Planned % for one scope.

    Prefers the SCHEDULE's own figure when the import carried one — P6's
    "Schedule % Complete", rolled up per scope by
    projects.services.scope_planned_map. That is what the client's reports
    quote as planned ("cumulative Plan Performance%"), and it is baseline-
    derived: a scope whose baseline finish has passed reads 100% no matter how
    far the live schedule has since slipped.

    The date-based fallback below is only for sources carrying no such column
    (zone trackers, older exports). On its own it was wrong on exactly the
    projects that matter: scope.planned_start/finish come from the P6
    Start/Finish columns, which are the CURRENT schedule, so elapsed time
    against them showed ~87% planned on a project whose baseline says 100% and
    which is over a year late (reported 2026-09-02).
    """
    if planned_map:
        from_schedule = planned_map.get(str(scope.id))
        if from_schedule is not None:
            return from_schedule
    start = scope.planned_start or project.planned_start
    finish = scope.planned_finish or project.planned_finish
    if not (start and finish and as_of and finish > start):
        return None
    frac = (as_of - start).days / (finish - start).days
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _hierarchy_rows(project, scope_ids=None, progress=None, prev_scopes=None, as_of=None, schedule_import=None):
    """Project -> Zone -> Subzone progress rollup (actual / previous / planned %)
    for the report's nested breakdown table. One level deeper than `_zone_rows`,
    using each scope's own planned dates when set. `prev_scopes` is the previous
    snapshot's full scope_id->% map (blank on snapshots taken before that existed,
    so deeper "previous" values may legitimately be missing). `schedule_import`
    pins the batch — see build_report_context's own resolution of it."""
    predicate, _ = _scope_context(project, scope_ids, schedule_import)
    prev_scopes = prev_scopes or {}
    # Baseline-derived planned %, keyed by scope id; empty for sources carrying
    # no such column, in which case _scope_planned_progress falls back to its
    # own date estimate exactly as before.
    planned_map = scope_planned_map(project, schedule_import)

    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    direct_w, direct_pw = {}, {}
    for sid, weight, prog, aid in activities.values_list("scope_id", "weight", "progress_percent", "id"):
        if not predicate(sid, aid):
            continue
        sid = str(sid)
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * prog

    scopes_qs = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    scopes = {str(s.id): s for s in scopes_qs}
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

    # Every ZONE-typed scope, regardless of depth — not just top-level ones;
    # see _zone_rows's docstring for why (Stage can sit above Zone).
    zones = sorted(
        (s for s in scopes.values() if s.scope_type == ProjectScope.ScopeType.ZONE),
        key=lambda s: (s.sort_order, s.name),
    )
    # See _disambiguated_names's docstring — the same "Z(A)" repeated under
    # different stages/buildings gets a disambiguating parent prefix here too.
    zone_display_name = _disambiguated_names((z.id, z.name, z.parent_id) for z in zones)
    # The zone's own parent (its stage), kept separately as well as folded into
    # the display name: the reference Progress Sheet puts the stage in its own
    # "Unit" column beside the zone, rather than prefixing it (2026-09-02).
    stage_names = dict(
        ProjectScope.objects.filter(id__in={z.parent_id for z in zones if z.parent_id})
        .values_list("id", "name")
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
                "planned": _scope_planned_progress(child, project, as_of, planned_map),
            })
        rows.append({
            "id": zid, "name": zone_display_name[zid], "actual": pct(zid), "previous": prev_scopes.get(zid),
            "planned": _scope_planned_progress(zone, project, as_of, planned_map),
            "stage": stage_names.get(zone.parent_id) or "",
            "zone": zone.name,
            "children": sub_rows,
        })
    return rows


def _phase_rows(project, scope_ids=None, progress=None, prev_scopes=None, as_of=None, schedule_import=None):
    """One row per STAGE-typed scope (the client's "Phase 1..5"), each with its
    own weighted progress and the zones under it as `children` — what the
    reference report's per-phase dashboard pages are built from (its pages
    33-37, 2026-08-30).

    Deliberately shares `_hierarchy_rows`' machinery rather than re-deriving
    a rollup: a phase's percentage has to be the activity-weighted average of
    everything beneath it, not the mean of its zones' percentages, or a phase
    holding one small zone and one huge one reports a figure that matches
    nothing else in the report."""
    predicate, _ = _scope_context(project, scope_ids, schedule_import)
    prev_scopes = prev_scopes or {}
    # Baseline-derived planned %, keyed by scope id; empty for sources carrying
    # no such column, in which case _scope_planned_progress falls back to its
    # own date estimate exactly as before.
    planned_map = scope_planned_map(project, schedule_import)

    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    direct_w, direct_pw = {}, {}
    # Budgeted and earned cost per scope, for the stage dashboard's Earned
    # Progress pie — P6's own EVM figures, summed the same way and rolled up
    # the same subtree as progress below.
    direct_budget, direct_earned = {}, {}
    for sid, weight_val, prog, aid, budget, earned in activities.values_list(
            "scope_id", "weight", "progress_percent", "id", "budgeted_cost", "earned_value_cost"):
        if not predicate(sid, aid):
            continue
        sid = str(sid)
        w = float(weight_val)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * prog
        if budget is not None:
            direct_budget[sid] = direct_budget.get(sid, 0.0) + float(budget)
        if earned is not None:
            direct_earned[sid] = direct_earned.get(sid, 0.0) + float(earned)

    scopes_qs = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    scopes = {str(s.id): s for s in scopes_qs}
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

    def cost(sid):
        """(budgeted, earned) over this scope's whole subtree."""
        b, e = direct_budget.get(sid, 0.0), direct_earned.get(sid, 0.0)
        for cid in children.get(sid, []):
            cb, ce = cost(cid)
            b += cb
            e += ce
        return b, e

    stages = sorted(
        (s for s in scopes.values() if s.scope_type == ProjectScope.ScopeType.STAGE),
        key=lambda s: (s.sort_order, s.name),
    )
    rows = []
    for stage in stages:
        sid = str(stage.id)
        agg(sid)
        if not weight.get(sid):
            continue
        kids = []
        for cid in sorted(children.get(sid, []), key=lambda c: (scopes[c].sort_order, scopes[c].name)):
            if not weight.get(cid):
                continue
            child = scopes[cid]
            kids.append({
                "name": child.name, "actual": pct(cid), "previous": prev_scopes.get(cid),
                "planned": _scope_planned_progress(child, project, as_of, planned_map),
            })
        # A stage's direct children are ZONES, but the reference dashboard's
        # planned-vs-actual bar chart plots one pair per AREA — the buildings
        # one level further down ("المرحلة الاولى (75) عمارة"). Collected
        # separately so `children` keeps meaning "direct children" for the
        # zone table beside it (2026-09-03).
        areas = []
        for zid in sorted(children.get(sid, []), key=lambda c: (scopes[c].sort_order, scopes[c].name)):
            for aid_ in sorted(children.get(zid, []), key=lambda c: (scopes[c].sort_order, scopes[c].name)):
                child = scopes[aid_]
                if child.scope_type != ProjectScope.ScopeType.AREA or not weight.get(aid_):
                    continue
                areas.append({
                    # Labelled with its zone, not just its own name — see
                    # _zone_area_label; "Building 6" alone names two bars.
                    "name": _zone_area_label(scopes[zid].name, child.name),
                    "area_name": child.name, "zone_name": scopes[zid].name,
                    "actual": pct(aid_), "previous": prev_scopes.get(aid_),
                    "planned": _scope_planned_progress(child, project, as_of, planned_map),
                })

        planned = _scope_planned_progress(stage, project, as_of, planned_map)
        actual = pct(sid)
        budgeted, earned = cost(sid)
        rows.append({
            "id": sid, "name": stage.name, "actual": actual, "previous": prev_scopes.get(sid),
            "planned": planned, "children": kids, "areas": areas,
            "budgeted_cost": budgeted, "earned_value_cost": earned,
            "duration": _zone_duration(stage, project, as_of, planned_pct=planned, actual_pct=actual),
        })
    return rows


def copy_layout_override(override):
    """Deep-copy a report's saved layout for a duplicate of that report.

    Two things are deliberately NOT carried across, both because the new
    report doesn't own them:

    * `upload_id` / `upload_url` on an image element point at a ReportImage
      belonging to the SOURCE report. The images aren't copied (a new month
      has new photos), so a verbatim copy would leave the duplicate pointing
      at another report's files — broken at best, a cross-report leak at
      worst. Those elements come back as an empty upload box.
    * `overrides` / `hidden_rows` on a table are keyed by row/column POSITION
      in last period's data. Re-applied to a new month's rows they would
      silently rewrite unrelated cells and drop unrelated rows, which is far
      worse than making the user redo a few edits.

    Page and element ids are kept: they're only ever meaningful inside one
    report's own layout blob, so duplicates across reports can't collide.
    """
    if not override:
        return None
    out = copy.deepcopy(override)
    for page in ((out.get("layout") or {}).get("pages")) or []:
        for el in page.get("elements") or []:
            _strip_report_bound_props(el)
    for el in ((out.get("page_design") or {}).get("master_elements")) or []:
        _strip_report_bound_props(el)
    return out


def _strip_report_bound_props(el):
    """Clear the props on one element that belong to the report it came from
    — see copy_layout_override for why each one can't travel."""
    props = el.get("props")
    if not isinstance(props, dict):
        return
    if el.get("type") == "image" and props.get("source") == "upload":
        props.pop("upload_id", None)
        props.pop("upload_url", None)
    if el.get("type") == "table":
        props.pop("overrides", None)
        props.pop("hidden_rows", None)


def _financial_percent_complete(project, schedule_import=None):
    """Project-wide financial % complete — sum(earned_value_cost) /
    sum(budgeted_cost) across every real P6-imported Activity (2026-08-30,
    backs the "Progress Comparison" bars' real "Earned Value %" figure,
    alongside the already-existing time-based `planned` % and physical
    `overall` % actual). `None`, not 0, when the project has no cost
    import at all — same "absence stays absence" rule as
    _boq_financial_progress right below. `schedule_import` pins the batch —
    see build_report_context's own resolution of it."""
    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    agg = activities.exclude(budgeted_cost=None).aggregate(b=Sum("budgeted_cost"), e=Sum("earned_value_cost"))
    budget = float(agg["b"] or 0)
    if not budget:
        return None
    return round(float(agg["e"] or 0) / budget * 100, 1)


def _boq_financial_progress(project, limit=12, schedule_import=None):
    """Per-BOQ-phase financial progress — the reference dashboard's
    "Financial Progress according to BOQ" bars (2026-08-30). Uses each
    Activity's own real P6-imported `budgeted_cost`/`earned_value_cost`
    (Activity IS the BOQ item model — see its own docstring; those fields
    are null, not zero, for a zone-tracker project with no such import, so
    this quietly returns nothing rather than fabricating figures for a
    project that never had cost data).

    Two percentages per phase, BOTH over the project's total budgeted cost so
    the pair is directly comparable on one axis, exactly as the reference
    chart plots them:
    - `budget_share`: this phase's share of the total budget (how much of the
      whole this trade represents). These sum to 100%.
    - `financial_percent`: this phase's earned_value_cost over that same
      total (how much of the WHOLE budget has been earned in this trade).
      These sum to the project's overall financial progress, and each one is
      necessarily <= its own budget share, which is what makes the shortfall
      readable at a glance.

    The second figure used to be earned over the phase's OWN budget. That is a
    real number too, but it is not what the reference plots and it does not
    belong on the same axis: a trade holding 2.9% of the budget showed an 87%
    bar next to a 2.9% one, so every small trade towered over the big ones and
    the chart could not be read as a comparison at all (2026-09-02). The
    per-phase completion figure is still recoverable as
    financial_percent / budget_share.

    Sorted by budget share descending, capped at `limit` phases so a P6
    export with dozens of phases doesn't produce an unreadable chart.
    `schedule_import` pins the batch — see build_report_context's own
    resolution of it."""
    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    total_budget = float(
        activities.exclude(phase_name="").exclude(budgeted_cost=None)
        .aggregate(t=Sum("budgeted_cost"))["t"] or 0
    )
    if not total_budget:
        return []
    rows = (
        activities.exclude(phase_name="").exclude(budgeted_cost=None)
        .values("phase_name").annotate(budget=Sum("budgeted_cost"), earned=Sum("earned_value_cost"))
        .order_by("-budget")[:limit]
    )
    out = []
    for r in rows:
        budget = float(r["budget"] or 0)
        earned = float(r["earned"] or 0)
        out.append({
            "name": r["phase_name"],
            "budget_share": round(budget / total_budget * 100, 1),
            "financial_percent": round(earned / total_budget * 100, 1),
        })
    return out


def _discipline_rows(project, scope_ids=None, progress=None, schedule_import=None):
    """Per-unit (subzone/building) progress, one column per PHASE.

    Returns `(columns, rows)` — the phase names actually present in this
    schedule, and one row per unit carrying that unit's progress in each.

    The columns are the schedule's own phases ("Internal Finishes", "ELEC",
    "F.Fighting", "Snag list", …), not the four fixed discipline tags this used
    to bucket them into. Those tags are a coarse classification of a phase, so
    every project ended up with the same five columns whatever its real work
    breakdown was — on a schedule with eight phases per building, two of the
    five columns were permanently empty and the other three merged unrelated
    work packages. The client asked for the tree's own phases instead, which is
    also what their scope tree shows under each unit (2026-09-02).

    Units with no phases are omitted. `schedule_import` pins the batch — see
    build_report_context's own resolution of it."""
    predicate, _ = _scope_context(project, scope_ids, schedule_import)

    scopes = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    phases = {
        str(s.id): s for s in scopes.filter(scope_type=ProjectScope.ScopeType.PHASE)
    }
    if not phases:
        return [], []

    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    unit_w, unit_pw = {}, {}
    # Column order follows the schedule's own ordering, not first-seen or
    # alphabetical, so the columns read in the sequence the work happens.
    seen_order = {}
    for sid, weight, prog, aid in activities.values_list("scope_id", "weight", "progress_percent", "id"):
        sid = str(sid)
        phase = phases.get(sid)
        if not phase or phase.parent_id is None or not predicate(sid, aid):
            continue
        key = phase.label or phase.name
        seen_order.setdefault(key, (phase.sort_order, key))
        unit_id = str(phase.parent_id)
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        unit_w.setdefault(unit_id, {}).setdefault(key, 0.0)
        unit_pw.setdefault(unit_id, {}).setdefault(key, 0.0)
        unit_w[unit_id][key] += w
        unit_pw[unit_id][key] += w * prog

    if not unit_w:
        return [], []
    columns = [k for _, k in sorted(seen_order.values())]

    units = {str(s.id): s for s in scopes.filter(id__in=unit_w.keys())}
    # A building name repeats across zones ("Building 30" exists under several),
    # so a table keyed on the bare name shows the same label twice on one page
    # with different numbers, reading as contradictory data (2026-08-30). Same
    # disambiguation `_hierarchy_rows` already applies to its zones.
    unit_display = _disambiguated_names((u.id, u.name, u.parent_id) for u in units.values())
    rows = []
    for uid, by_phase in sorted(unit_w.items(), key=lambda kv: (units[kv[0]].sort_order, units[kv[0]].name)):
        row = {"name": unit_display.get(uid, units[uid].name), "values": []}
        for key in columns:
            w = by_phase.get(key, 0.0)
            row["values"].append(round(unit_pw[uid][key] / w, 1) if w else None)
        rows.append(row)
    return columns, rows


def _subtree_ids(project, root_id, schedule_import=None):
    """All scope ids in the subtree rooted at root_id (inclusive).
    `schedule_import` pins the batch — see build_report_context's own
    resolution of it."""
    scopes = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    children = {}
    for sid, pid in scopes.values_list("id", "parent_id"):
        if pid:
            children.setdefault(str(pid), []).append(str(sid))
    out, stack = [], [str(root_id)]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(children.get(node, []))
    return out


def _gantt_rows(project, scope_ids=None, progress=None, schedule_import=None):
    """Zone + direct-child bars for a simple Gantt-style schedule printout.
    Each row's baseline span is its OWN planned_start/planned_finish (set via
    manual entry or the schedule import) — we don't fall back to the project's
    dates the way `_zone_duration` does, since every row would then render an
    identical full-project bar. Rows without both dates are simply omitted.
    No predecessor/float/critical-path computation: the fill just shows the
    row's own rolled-up actual % complete. `schedule_import` pins the batch —
    see build_report_context's own resolution of it."""
    predicate, _ = _scope_context(project, scope_ids, schedule_import)

    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    direct_w, direct_pw = {}, {}
    for sid, weight, prog, aid in activities.values_list("scope_id", "weight", "progress_percent", "id"):
        if not predicate(sid, aid):
            continue
        sid = str(sid)
        w = float(weight)
        prog = progress.get(str(aid), float(prog)) if progress is not None else float(prog)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * prog

    scopes_qs = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    scopes = {str(s.id): s for s in scopes_qs}
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

    # Every ZONE-typed scope, regardless of depth — not just top-level ones;
    # see _zone_rows's docstring for why (Stage can sit above Zone).
    zones = sorted(
        (s for s in scopes.values() if s.scope_type == ProjectScope.ScopeType.ZONE),
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


def _selected_progress_photos(report, project):
    """Progress photos hand-picked in the builder (report.progress_image_ids),
    returned as {image, caption} dicts ordered by date — earliest first, so the
    report's first photo page is the oldest — like the user asked."""
    ids = report.progress_image_ids or []
    if not ids:
        return []
    from apps.projects.models import ProgressImage

    rows = ProgressImage.objects.filter(entry__project=project, id__in=ids).values(
        "id", "image", "caption", "entry__date", "created_at")
    ordered = sorted(rows, key=lambda p: (p["entry__date"] or datetime.date.min, p["created_at"]))
    return [{"image": p["image"], "caption": p["caption"],
             "url": f"/api/projects/{project.id}/progress-images/{p['id']}/file/"} for p in ordered]


def _area_dashboards(project, hierarchy, as_of, schedule_import=None):
    """Per-zone dashboard data: its own duration/time-performance (falls back
    to the project's when it has none of its own) and a handful of recent
    progress photos from its subtree. The planned-vs-actual bar chart is drawn
    straight from `hierarchy`'s children, so this only adds what that doesn't.
    `schedule_import` pins the batch — see build_report_context's own
    resolution of it. `hierarchy`'s own zone ids are already scoped to it, so
    this mainly matters for the `_subtree_ids` lookup below."""
    from apps.projects.models import ProgressImage

    zone_ids = [z["id"] for z in hierarchy]
    scopes = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    zones_by_id = {str(s.id): s for s in scopes.filter(id__in=zone_ids)}

    out = []
    for z in hierarchy:
        zone = zones_by_id.get(z["id"])
        if not zone:
            continue
        subtree = _subtree_ids(project, z["id"], schedule_import)
        photos = list(
            ProgressImage.objects.filter(entry__project=project, entry__activity__scope_id__in=subtree)
            .order_by("-entry__date", "-created_at")
            .values("image", "caption")[:4]
        )
        # Only show a per-zone duration when the zone carries its own schedule —
        # otherwise `_zone_duration` falls back to the project's dates and every
        # zone page would repeat the same pie (already on the exec dashboard).
        own_schedule = bool(zone.planned_start and zone.planned_finish)
        out.append({
            "name": z["name"], "actual": z["actual"], "planned": z["planned"],
            "children": z["children"],
            "duration": _zone_duration(zone, project, as_of, planned_pct=z["planned"], actual_pct=z["actual"])
            if own_schedule else None,
            "photos": photos,
        })
    return out


def _critical_path_rows(project, hierarchy, as_of, schedule_import=None):
    """Per-zone baseline finish vs current forecast, for zones carrying their
    own P6-imported schedule (planned_start/finish) — the "which buildings
    are slipping and by how much" table. `schedule_import` pins the batch —
    see build_report_context's own resolution of it.

    Delay/forecast come straight from `_zone_duration` (see its own and
    `_duration_for`'s docstrings for the 3-signal priority: explicit
    revised_finish, then officially-overdue, then a pace-based estimate) —
    passing this zone's real planned/actual % is what makes signal 3 available
    here, the fix for a real bug (found 2026-08-25): every zone in a real,
    badly slipping project showed exactly 0 days delay simply because none of
    their individual deadlines had technically arrived yet, even though the
    project-level dashboard (a different, already-correct calculation)
    reported months of real slippage for the same project."""
    zone_ids = [z["id"] for z in hierarchy]
    scopes = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    zones_by_id = {str(s.id): s for s in scopes.filter(id__in=zone_ids)}
    rows = []
    for z in hierarchy:
        zone = zones_by_id.get(z["id"])
        if not zone or not (zone.planned_start and zone.planned_finish):
            continue
        dur = _zone_duration(zone, project, as_of, planned_pct=z.get("planned"), actual_pct=z.get("actual"))
        if not dur:
            continue
        delay = dur["delay"]
        if zone.revised_finish and zone.revised_finish > zone.planned_finish:
            forecast = zone.revised_finish
        else:
            forecast = zone.planned_finish + datetime.timedelta(days=delay) if delay else zone.planned_finish
        rows.append({
            "name": z["name"],
            "planned_finish": zone.planned_finish,
            "forecast_finish": forecast,
            "delay_days": delay,
        })
    return rows


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
    # Which schedule-import batch "current" means for this report — reusing
    # `as_of` (already "the report's as-of date", used for the progress-entry
    # lookup right below) for schedule-import resolution too: they're the
    # same underlying question ("what date is this report as of"), so a
    # report left at its default (as_of = today) always floats to the
    # latest import, and one explicitly dated in the past pins to whatever
    # was current as of that date — exactly the "auto-latest unless
    # overridden" behavior asked for (2026-08-30), with no separate field.
    # See ScheduleImport's own docstring for why this matters: a re-import
    # no longer deletes the previous batch, so without this every report
    # would silently start double-counting activities from every batch ever
    # imported combined, the moment a project gets re-imported a second time.
    schedule_import = latest_schedule_import(project, as_of=as_of)
    # Part Scope is a log (see PartScope's docstring) — the report shows
    # whichever entry is most recent, ordered by the model's own Meta.
    latest_part = project.part_scopes.first()

    # As-of-date progress: read each activity's % from its latest dated entry on
    # or before the report date. Empty (no entries anywhere) → fast current path.
    progress = activity_progress_as_of(project, as_of) or None

    overall = project_overall_progress(project, progress, schedule_import)
    breakdown = _breakdown(project, progress, schedule_import)

    planned = _planned_progress(project, as_of, use_imported=(progress is None))
    duration = _duration(project, as_of)

    milestones = list(
        project.milestones.order_by("sort_order", "date").values("title", "date", "status")
    )
    snapshots = list(
        project.snapshots.order_by("date")
        .values("date", "overall_progress", "source", "zones", "scopes",
                "planned_progress", "forecast_progress")
    )

    # Previous actual = the most recent snapshot strictly before the report date.
    prev_snap = next(
        (s for s in reversed(snapshots) if s["date"] and s["date"] < as_of), None
    )
    prev_zone = {z.get("name"): z.get("progress") for z in (prev_snap["zones"] or [])} if prev_snap else {}
    prev_scopes_map = (prev_snap.get("scopes") or {}) if prev_snap else {}
    prev_overall = float(prev_snap["overall_progress"]) if prev_snap else None
    # "Project Tracking" bars (2026-08-30 — previous month vs. current month,
    # planned vs. actual): reuses prev_overall/overall/planned above rather
    # than a new query. `previous.actual` is None (not 0 — see
    # progress_tracking_chart) when there's no snapshot before as_of at all,
    # e.g. a project's very first report.
    monthly_tracking = {
        "previous": {"planned": planned, "actual": prev_overall},
        "current": {"planned": planned, "actual": overall},
    }

    # Scope-aware: only zones with selected tasks appear; progress rolls up over
    # the selected tasks (empty selection = whole project).
    zones = _zone_rows(project, report.scope_ids, progress, schedule_import)
    for z in zones:
        z["previous"] = prev_zone.get(z["name"])
        z["planned"] = planned  # time-based baseline is project-wide

    # Project -> Zone -> Subzone breakdown (one level deeper than `zones` above).
    hierarchy = _hierarchy_rows(project, report.scope_ids, progress, prev_scopes_map, as_of, schedule_import)
    # Flat list of areas (the subzones under every zone) for the optional
    # area-level planned/actual bar chart.
    areas = [{"name": c["name"], "planned": c["planned"], "actual": c["actual"]}
             for z in hierarchy for c in z["children"]]
    discipline_columns, discipline = _discipline_rows(project, report.scope_ids, progress, schedule_import)
    boq_financial_progress = _boq_financial_progress(project, schedule_import=schedule_import)
    financial_percent_complete = _financial_percent_complete(project, schedule_import)
    area_dashboards = _area_dashboards(project, hierarchy, as_of, schedule_import)
    # Per-phase (STAGE scope) rollups — backs the reference report's own
    # per-phase dashboard pages. Same inputs as `hierarchy`, one level up.
    phase_dashboards = _phase_rows(project, report.scope_ids, progress, prev_scopes_map, as_of, schedule_import)
    critical_path = _critical_path_rows(project, hierarchy, as_of, schedule_import)
    gantt = _gantt_rows(project, report.scope_ids, progress, schedule_import)

    # Grids are heavy (tens of thousands of cells); the PDF computes them lazily
    # only when the detailed-progress section is enabled.
    zone_grids = []

    delays = list(
        project.delays.order_by("sort_order", "-date").values("title", "description", "impact_days", "status", "date")
    )

    # Finances — user-entered monthly cash flow (we add it up for the cumulative
    # S-curve) and invoices. Values are stored as-is; nothing is computed here.
    cum_p = cum_a = 0.0
    cashflow = []
    for e in project.cashflow_entries.order_by("month").values("month", "planned", "actual"):
        p, a = float(e["planned"]), float(e["actual"])
        cum_p += p
        cum_a += a
        cashflow.append({"month": e["month"], "planned": p, "actual": a,
                         "cum_planned": cum_p, "cum_actual": cum_a})
    cashflow_totals = {"planned": cum_p, "actual": cum_a}

    invoices = [
        {"name": i["name"], "value": float(i["value"]), "date": i["date"]}
        for i in project.invoices.order_by("sort_order", "-date").values("name", "value", "date")
    ]
    invoices_total = sum(i["value"] for i in invoices)

    # Approved Cost Variation Orders — the "new items" (added/omitted work)
    # slice of a Budget Total Cost breakdown. Only APPROVED ones count: a
    # pending/rejected VO hasn't actually changed the contract value yet
    # (matches Variation.__doc__'s own "effect only applies once APPROVED").
    variations_cost_approved_total = float(
        project.variations.filter(kind=Variation.Kind.COST, status=Variation.Status.APPROVED)
        .aggregate(s=Sum("amount"))["s"] or 0
    )

    # Submittals — table rows plus a status summary (counts per approval status).
    status_labels = dict(Submittal.Status.choices)
    type_labels = dict(Submittal.Type.choices)
    disc_labels = dict(Submittal.Discipline.choices)
    sub_rows = list(project.submittals.order_by("sort_order", "-date").values(
        "title", "submittal_type", "discipline", "status", "reference", "date"))
    status_counts = {}
    for s in sub_rows:
        status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1
    submittals = {
        "rows": [{"title": s["title"], "type": type_labels.get(s["submittal_type"], ""),
                  "type_key": s["submittal_type"],
                  "discipline": disc_labels.get(s["discipline"], ""),
                  "status": status_labels.get(s["status"], ""), "status_key": s["status"],
                  "reference": s["reference"], "date": s["date"]} for s in sub_rows],
        "summary": [{"status": label, "key": key, "count": status_counts.get(key, 0)}
                    for key, label in status_labels.items()],
    }

    # S-curve series: actual, planned and forecast at each snapshot date.
    #
    # Planned and forecast come from the SCHEDULE's own curve when the source
    # carried one (a P6 progress-curve sheet). Those are cost-loaded, so they
    # bend the way a real programme does; the date-based fallback is a straight
    # line between two dates, which is not what the client's curve looks like
    # and reads wrong on any front- or back-loaded job (2026-09-02).
    scurve = [
        {
            "date": s["date"],
            "actual": float(s["overall_progress"]),
            "planned": (float(s["planned_progress"]) if s["planned_progress"] is not None
                        else _planned_progress(project, s["date"])),
            "forecast": (float(s["forecast_progress"])
                         if s["forecast_progress"] is not None else None),
        }
        for s in snapshots if s["date"]
    ]
    # Logos stay on the project (constant branding); the cover/photos/attachments
    # are per-report content that overrides any project-level fallback.
    proj_images = list(
        project.images.order_by("image_type", "sort_order", "created_at")
        .values("id", "image_type", "caption", "image")
    )
    rep_images = list(
        report.images.order_by("kind", "sort_order", "created_at").values("id", "kind", "caption", "image")
    )
    # `image` stays the raw FieldFile path the PDF renderer embeds directly;
    # `url` is the private, authed streaming endpoint (see ProjectImageFileView/
    # ReportImageViewSet) the Customize tab's canvas can put in an <img src>
    # without exposing a public bucket URL.
    for i in proj_images:
        i["url"] = f"/api/projects/{project.id}/images/{i['id']}/file/"
    for i in rep_images:
        i["url"] = f"/api/reports/{report.id}/images/{i['id']}/file/"

    def proj(kind):
        return next((i for i in proj_images if i["image_type"] == kind), None)

    def proj_many(kind):
        return [i for i in proj_images if i["image_type"] == kind]

    def rep(kind):
        return [i for i in rep_images if i["kind"] == kind]

    rep_cover = rep(ReportImage.Kind.COVER)
    rep_photos = rep(ReportImage.Kind.PROGRESS)
    attachments = rep(ReportImage.Kind.ATTACHMENT)
    # Progress photos hand-picked in the builder from the schedule tab's
    # submissions — rendered earliest date first, before any manual uploads.
    selected_photos = _selected_progress_photos(report, project)

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
            "contractor_consultant": project.contractor_consultant,
            "planned_start": project.planned_start,
            "planned_finish": project.planned_finish,
            "revised_finish": project.revised_finish,
            "forecast_finish": project.forecast_finish,
            "size_sqm": project.size_sqm,
            "budget": project.budget,
            "budget_currency": project.budget_currency,
            "advance_payment": project.advance_payment,
            "advance_payment_currency": project.advance_payment_currency,
            "eot_days": project.eot_days,
            "contract_value": project.contract_value,
            "contract_value_currency": project.contract_value_currency,
            "approved_value": project.approved_value,
            "approved_value_currency": project.approved_value_currency,
            "forecast_cost": project.forecast_cost,
            "forecast_cost_currency": project.forecast_cost_currency,
            "part_amount": latest_part.amount if latest_part else None,
            "part_completion_revised": latest_part.completion_revised if latest_part else None,
            "part_forecast_completion": latest_part.forecast_completion if latest_part else None,
            "part_delay_days": latest_part.delay_days if latest_part else None,
            "currency": project.currency,
            "notes": project.notes,
        },
        "overall": overall,
        "planned": planned,
        "previous_overall": prev_overall,
        "monthly_tracking": monthly_tracking,
        "duration": duration,
        "breakdown": breakdown,
        "zones": zones,
        "areas": areas,
        "hierarchy": hierarchy,
        "discipline": discipline,
        "discipline_columns": discipline_columns,
        "boq_financial_progress": boq_financial_progress,
        "financial_percent_complete": financial_percent_complete,
        "area_dashboards": area_dashboards,
        "phase_dashboards": phase_dashboards,
        "critical_path": critical_path,
        "gantt": gantt,
        "zone_grids": zone_grids,
        # Internal: as-of progress map so the PDF's lazy grid matches the report
        # date (None when the project has no dated entries).
        "_progress": progress,
        "cashflow": cashflow,
        "cashflow_totals": cashflow_totals,
        "invoices": invoices,
        "invoices_total": invoices_total,
        "variations_cost_approved_total": variations_cost_approved_total,
        "submittals": submittals,
        "delays": delays,
        "scurve": scurve,
        # The report's own as-of date, so a chart can tell "already happened"
        # from "still ahead" — the progress curve splits its actual line from
        # its forecast run-out here (see pdf_charts.scurve_chart).
        "as_of": as_of,
        "milestones": milestones,
        "snapshots": snapshots,
        "logos": {
            "left": proj(ProjectImage.ImageType.LOGO_LEFT),
            "right": proj(ProjectImage.ImageType.LOGO_RIGHT),
            "cover": (rep_cover[0] if rep_cover else proj(ProjectImage.ImageType.COVER)),
            # Beyond the two fixed header slots — any number of extra partner/
            # funding/authority logos, in upload (sort_order) order.
            "extra": proj_many(ProjectImage.ImageType.LOGO),
        },
        "photos": (selected_photos + rep_photos)
        or [i for i in proj_images if i["image_type"] == ProjectImage.ImageType.SITE_PHOTO],
        "attachments": attachments,
    }
