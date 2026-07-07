"""Project business logic — progress roll-up from activities."""
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

_WEIGHTED = ExpressionWrapper(
    F("progress_percent") * F("weight"), output_field=DecimalField(max_digits=20, decimal_places=4)
)


def activity_progress_as_of(project, as_of) -> dict:
    """Map {activity_id(str) -> progress %} reflecting a point in time.

    Activities with dated progress entries use the latest entry on/before
    `as_of` (0 if they have entries but none yet by that date — work hadn't been
    recorded). Activities with no entries at all are omitted, so callers fall
    back to the current denormalized % (e.g. an import baseline never recorded
    as a dated entry). Empty dict when the project has no entries → callers use
    the fast DB-aggregate path."""
    from .models import ProgressEntry

    latest = (
        ProgressEntry.objects.filter(project=project, date__lte=as_of)
        .order_by("activity_id", "-date", "-created_at")
        .distinct("activity_id")
        .values_list("activity_id", "progress_percent")
    )
    result = {str(aid): float(p) for aid, p in latest}
    # Activities with entries but none on/before as_of read as 0 (not baseline).
    entried = ProgressEntry.objects.filter(project=project).values_list("activity_id", flat=True).distinct()
    for aid in entried:
        result.setdefault(str(aid), 0.0)
    return result


def project_overall_progress(project, progress=None) -> float:
    """Weighted overall progress (0–100): sum(progress*weight)/sum(weight)
    across the project's activities. 0 when there are none. When `progress`
    (an activity_id->% map, e.g. as-of-date) is given, the DB aggregate is
    computed once and then *corrected* only for the few overridden activities —
    never iterate the whole table (projects hold tens of thousands of rows)."""
    agg = project.activities.aggregate(wsum=Sum("weight"), psum=Sum(_WEIGHTED))
    wsum = float(agg["wsum"] or 0)
    if not wsum:
        return 0.0
    psum = float(agg["psum"] or 0)
    if progress:
        for aid, w, cur in project.activities.filter(
            id__in=list(progress.keys())
        ).values_list("id", "weight", "progress_percent"):
            psum += float(w) * (progress[str(aid)] - float(cur))
    return round(psum / wsum, 1)


def _planned_at(project, on):
    """Time-based planned % (0–100) for a date: 0 at the planned start rising
    straight to 100 at the planned finish. None when the project has no dates."""
    s, f = project.planned_start, project.planned_finish
    if not (s and f and on and f > s):
        return None
    frac = (on - s).days / (f - s).days
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def progress_series(project, max_points=60) -> list:
    """Actual-vs-planned overall progress over time, computed *live* from the
    project's current data — not a static per-import capture. Points come from:
      • each dated Update reading (ProgressEntry) — reflects manual progress edits,
      • each import snapshot (ProgressSnapshot) — reflects imported baselines,
      • a live "today" point from the current overall,
    so the chart moves whenever progress or the planned dates change. Planned is
    derived from the project's dates, so editing them updates the baseline too."""
    from django.utils import timezone

    from .models import ProgressEntry

    actual = {}  # date -> overall %

    # Import baselines (their captured overall on that date).
    for s in project.snapshots.values("date", "overall_progress"):
        if s["date"]:
            actual[s["date"]] = float(s["overall_progress"])

    # Manual Update history: overall as-of each distinct reading date (most recent
    # dates win if capped). Overrides a same-date snapshot with the live rollup.
    entry_dates = sorted(set(
        ProgressEntry.objects.filter(project=project)
        .values_list("date", flat=True).distinct()
    ))
    for d in entry_dates[-max_points:]:
        actual[d] = project_overall_progress(project, activity_progress_as_of(project, d))

    # Always include a live "today" point so the latest state is current.
    today = timezone.now().date()
    actual[today] = project_overall_progress(project, activity_progress_as_of(project, today))

    dates = sorted(actual)[-max_points:]
    return [
        {"date": d, "overall_progress": round(actual[d], 1), "planned": _planned_at(project, d)}
        for d in dates
    ]


def _month_bounds(any_date):
    """(day before the month starts, last day of that month) for a given date."""
    import datetime as _dt

    first = any_date.replace(day=1)
    day_before = first - _dt.timedelta(days=1)
    nxt = (first.replace(year=first.year + 1, month=1)
           if first.month == 12 else first.replace(month=first.month + 1))
    return day_before, nxt - _dt.timedelta(days=1)


def view_progress_map(project, mode, as_of):
    """Per-activity {id(str) -> %} override for a Schedule view mode, or None for
    'current' (live values):
      • 'asof'  — cumulative % on/before as_of. Sparse: only activities with dated
        readings; others fall back to their current % (imports carry no per-activity
        history, so they read as current).
      • 'month' — % gained during as_of's month (end − start). A complete map with
        0 where nothing moved / no reading exists.
    """
    if mode == "asof" and as_of:
        return activity_progress_as_of(project, as_of)
    if mode == "month" and as_of:
        day_before, last = _month_bounds(as_of)
        start = activity_progress_as_of(project, day_before)
        end = activity_progress_as_of(project, last)
        out = {}
        for aid, cur in project.activities.values_list("id", "progress_percent"):
            s = str(aid)
            c = float(cur)
            out[s] = round(end.get(s, c) - start.get(s, c), 2)
        return out
    return None


def breakdown_from_map(project, value_map) -> dict:
    """Activity counts by state (completed/in-progress/not-started) using an
    override map; activities missing from the map use their current %."""
    total = completed = not_started = 0
    for aid, cur in project.activities.values_list("id", "progress_percent"):
        v = value_map.get(str(aid), float(cur))
        total += 1
        if v >= 100:
            completed += 1
        elif v <= 0:
            not_started += 1
    return {"total": total, "completed": completed, "not_started": not_started,
            "in_progress": total - completed - not_started}


def scope_progress_map(project, progress=None) -> dict:
    """Map of scope_id -> weighted progress rolled up over the scope's *whole
    subtree*. Computed on the backend so the tree shows real progress without
    shipping every activity (zone trackers have tens of thousands of cells).
    `progress` (activity_id->% map) overrides current values when given."""
    direct_w, direct_pw = {}, {}
    for aid, sid, w, p in project.activities.values_list("id", "scope_id", "weight", "progress_percent"):
        w = float(w)
        p = progress.get(str(aid), float(p)) if progress is not None else float(p)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * p

    children, all_ids = {}, []
    roots = []
    for sid, pid in project.scopes.values_list("id", "parent_id"):
        all_ids.append(sid)
        if pid is None:
            roots.append(sid)
        else:
            children.setdefault(pid, []).append(sid)

    sub_w, sub_pw = {}, {}

    def agg(sid):
        w, pw = direct_w.get(sid, 0.0), direct_pw.get(sid, 0.0)
        for child in children.get(sid, []):
            cw, cpw = agg(child)
            w += cw
            pw += cpw
        sub_w[sid], sub_pw[sid] = w, pw
        return w, pw

    for r in roots:
        agg(r)

    return {
        str(sid): (round(sub_pw[sid] / sub_w[sid], 1) if sub_w.get(sid) else 0.0)
        for sid in all_ids
    }
