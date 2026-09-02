"""Project business logic — progress roll-up from activities."""
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

_WEIGHTED = ExpressionWrapper(
    F("progress_percent") * F("weight"), output_field=DecimalField(max_digits=20, decimal_places=4)
)


def latest_schedule_import(project, as_of=None):
    """The schedule-import batch "current" means for this project right now —
    the most recent one, or (when `as_of` is given) the most recent one whose
    own `date` isn't after `as_of`. `None` ONLY when the project has never had
    a schedule import at all (a hand-built project, or one whose only data is
    a raw zone-tracker import predating this feature — see ScheduleImport's
    own docstring). Every function that reads "the project's activities/
    scopes" for anything current-state-shaped resolves this first and filters
    to it, so a re-import (which now creates a new batch instead of deleting
    the old one) can't silently double-count both generations together.

    Never returns None for a project that HAS batches, even when `as_of`
    predates every one of them. Callers all share the shape
    `filter(schedule_import=batch) if batch else .all()`, so a None here
    doesn't mean "no data" to them — it means "don't filter", i.e. read every
    batch ever imported, combined. That is exactly the double-count this
    function exists to prevent: a report dated before the first import came
    back with its zones duplicated once per batch and its activity weights
    summed across all of them (found 2026-08-30 on a report dated 3 Mar 2026
    against batches dated 11/30 Aug 2026 — 15 zones rendered as 30). When
    `as_of` is earlier than every batch, the earliest batch is the closest
    thing to the requested date, so that's what it falls back to."""
    from .models import ScheduleImport

    qs = ScheduleImport.objects.filter(project=project)
    if as_of is not None:
        on_or_before = qs.filter(date__lte=as_of).order_by("-date", "-created_at").first()
        if on_or_before is not None:
            return on_or_before
        return qs.order_by("date", "created_at").first()
    return qs.order_by("-date", "-created_at").first()


def resync_revised_finish(project) -> None:
    """Keep the project's revised finish equal to the latest APPROVED schedule
    Variation's (SVO's) new finish. Only approved variations count — a
    pending/rejected one has no effect. Left untouched when there are no
    approved schedule VOs (there's no sensible "reset" target)."""
    from .models import Variation

    latest = (project.variations
              .filter(kind=Variation.Kind.SCHEDULE, status=Variation.Status.APPROVED, new_finish__isnull=False)
              .order_by("-created_at").first())
    if latest and project.revised_finish != latest.new_finish:
        project.revised_finish = latest.new_finish
        project.save(update_fields=["revised_finish", "updated_at"])


def resync_approved_value(project) -> None:
    """Keep approved_value equal to contract_value plus the sum of all APPROVED
    cost Variations (CVOs) — the single source of truth for "what's approved
    after variations to date", rather than a second hand-typed figure that can
    drift from the actual Variation log. Cost VOs accumulate (each is a signed
    delta), unlike schedule VOs which replace a single date — see
    resync_revised_finish. A no-op until contract_value is set, since summing
    deltas onto nothing isn't a meaningful contract total."""
    from .models import Variation

    if project.contract_value is None:
        return
    total = project.variations.filter(
        kind=Variation.Kind.COST, status=Variation.Status.APPROVED,
    ).aggregate(total=Sum("amount"))["total"] or 0
    new_value = project.contract_value + total
    new_currency = project.contract_value_currency
    if project.approved_value != new_value or project.approved_value_currency != new_currency:
        project.approved_value = new_value
        project.approved_value_currency = new_currency
        # A queryset .update(), not project.save() — this runs from inside
        # Project.save() itself (so every code path that touches
        # contract_value stays correct, not just the ones that remember to
        # call this explicitly); .save() here would recurse.
        type(project).objects.filter(pk=project.pk).update(
            approved_value=new_value, approved_value_currency=new_currency, updated_at=timezone.now(),
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


def project_overall_progress(project, progress=None, schedule_import=None) -> float:
    """Weighted overall progress (0–100): sum(progress*weight)/sum(weight)
    across the project's activities. 0 when there are none. When `progress`
    (an activity_id->% map, e.g. as-of-date) is given, the DB aggregate is
    computed once and then *corrected* only for the few overridden activities —
    never iterate the whole table (projects hold tens of thousands of rows).

    `schedule_import` pins which import batch's activities to weight over —
    resolved to the latest one (`latest_schedule_import`) when not given.
    Every existing caller's behavior is unchanged from before batches
    existed; a caller can also pass the latest batch explicitly (e.g. right
    after creating it during import) without losing the shortcut below.

    A "current" call (no as-of override, batch resolves to the latest one —
    whether by leaving `schedule_import` unset or by passing it in
    explicitly) defers to imported_progress_percent when the project has
    one — a real P6 schedule states its own overall %, and that's a better
    number than our weighted approximation of it. That field only ever
    reflects the *latest* import though, so a call explicitly pinned to an
    OLDER batch always computes live instead."""
    latest = latest_schedule_import(project)
    if schedule_import is None:
        schedule_import = latest
    if progress is None and schedule_import == latest and project.imported_progress_percent is not None:
        return float(project.imported_progress_percent)
    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    agg = activities.aggregate(wsum=Sum("weight"), psum=Sum(_WEIGHTED))
    wsum = float(agg["wsum"] or 0)
    if not wsum:
        return 0.0
    psum = float(agg["psum"] or 0)
    if progress:
        for aid, w, cur in activities.filter(
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
        schedule_import = latest_schedule_import(project)
        activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
        for aid, cur in activities.values_list("id", "progress_percent"):
            s = str(aid)
            c = float(cur)
            out[s] = round(end.get(s, c) - start.get(s, c), 2)
        return out
    return None


def breakdown_from_map(project, value_map, schedule_import=None) -> dict:
    """Activity counts by state (completed/in-progress/not-started) using an
    override map; activities missing from the map use their current %.
    `schedule_import` — see project_overall_progress's own docstring;
    resolved to latest when not given."""
    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    total = completed = not_started = 0
    for aid, cur in activities.values_list("id", "progress_percent"):
        v = value_map.get(str(aid), float(cur))
        total += 1
        if v >= 100:
            completed += 1
        elif v <= 0:
            not_started += 1
    return {"total": total, "completed": completed, "not_started": not_started,
            "in_progress": total - completed - not_started}


def scope_planned_map(project, schedule_import=None) -> dict:
    """Map of scope_id -> weighted PLANNED % over the scope's whole subtree.

    The same rollup as scope_progress_map, over each activity's own
    `schedule_percent` (P6's "Schedule % Complete") instead of its actual
    progress. Only scopes with at least one activity carrying that column get
    an entry — callers fall back to their own estimate for the rest, so a zone
    tracker with no such column behaves exactly as it did before.

    This exists because planned % must come from the BASELINE, not from elapsed
    calendar time against the live schedule: the live dates have already
    absorbed every delay, so time-elapsed against them showed ~87% planned on a
    project whose baseline says 100% and which is over a year late (2026-09-02).
    """
    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    activities = (project.activities.filter(schedule_import=schedule_import)
                  if schedule_import else project.activities.all())
    direct_w, direct_pw = {}, {}
    for sid, w, sp in activities.exclude(schedule_percent=None).values_list(
            "scope_id", "weight", "schedule_percent"):
        w = float(w)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * float(sp)
    if not direct_w:
        return {}

    scopes = (project.scopes.filter(schedule_import=schedule_import)
              if schedule_import else project.scopes.all())
    children, all_ids, roots = {}, [], []
    for sid, pid in scopes.values_list("id", "parent_id"):
        all_ids.append(sid)
        (roots if pid is None else children.setdefault(pid, [])).append(sid)

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

    # No entry (rather than 0.0) for a scope whose subtree carried none of the
    # column — 0% planned and "unknown" are very different things on a report.
    return {str(sid): round(sub_pw[sid] / sub_w[sid], 1)
            for sid in all_ids if sub_w.get(sid)}


def scope_progress_map(project, progress=None, schedule_import=None) -> dict:
    """Map of scope_id -> weighted progress rolled up over the scope's *whole
    subtree*. Computed on the backend so the tree shows real progress without
    shipping every activity (zone trackers have tens of thousands of cells).
    `progress` (activity_id->% map) overrides current values when given.
    `schedule_import` — see project_overall_progress's own docstring;
    resolved to latest when not given."""
    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    activities = project.activities.filter(schedule_import=schedule_import) if schedule_import else project.activities.all()
    scopes = project.scopes.filter(schedule_import=schedule_import) if schedule_import else project.scopes.all()
    direct_w, direct_pw = {}, {}
    for aid, sid, w, p in activities.values_list("id", "scope_id", "weight", "progress_percent"):
        w = float(w)
        p = progress.get(str(aid), float(p)) if progress is not None else float(p)
        direct_w[sid] = direct_w.get(sid, 0.0) + w
        direct_pw[sid] = direct_pw.get(sid, 0.0) + w * p

    children, all_ids = {}, []
    roots = []
    for sid, pid in scopes.values_list("id", "parent_id"):
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
