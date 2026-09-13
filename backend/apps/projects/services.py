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
    `as_of` is earlier than every batch, the earliest DATE is the closest
    thing to the requested date, so that's what it falls back to — but among
    several imports sharing that date it takes the LAST one uploaded, same
    tie-break as the on-or-before branch above. A re-import is a restatement
    of the same schedule, not a second schedule, so the newest upload for a
    date supersedes the earlier ones no matter which side of `as_of` it sits
    on. Ordering the fallback by `created_at` ascending instead made a report
    dated before its imports read the FIRST upload of that day: a July report
    on a project imported twice on 7 Sep rendered the 08:55 upload — a
    different project's workbook, uploaded by mistake and immediately
    corrected at 09:01 — so the Cairo airport report came out full of
    Mansoura's buildings and zones (2026-09-07)."""
    from .models import ScheduleImport

    qs = ScheduleImport.objects.filter(project=project)
    if as_of is not None:
        on_or_before = qs.filter(date__lte=as_of).order_by("-date", "-created_at").first()
        if on_or_before is not None:
            return on_or_before
        return qs.order_by("date", "-created_at").first()
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
    # Earned value is the reported figure wherever the schedule carries cost
    # (see project_earned_progress). It deliberately ignores `progress`: field
    # submissions and dated entries still flow through the review chain and
    # still update Activity.progress_percent, they just no longer move the
    # headline — one number on the page, reconcilable against the planners'
    # own dashboard cell by cell.
    earned = project_earned_progress(project, schedule_import)
    if earned is not None:
        return earned
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


def _planned_cost_rows(project, schedule_import=None):
    """(scope_id, planned cost, budget) per activity carrying BOTH the baseline
    percentage and a budget — the only rows planned cost is defined for.

    An activity with a budget but no `schedule_percent` is left out of both
    figures rather than counted as zero planned: "the baseline says nothing
    about this row" and "the baseline says this row should not have started"
    are different claims, and averaging them together understates the plan."""
    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    activities = (project.activities.filter(schedule_import=schedule_import)
                  if schedule_import else project.activities.all())
    for sid, pct, budget in (activities.exclude(schedule_percent=None)
                             .exclude(budgeted_cost=None)
                             .values_list("scope_id", "schedule_percent", "budgeted_cost")):
        budget = float(budget)
        yield sid, float(pct) / 100 * budget, budget


def project_planned_cost(project, schedule_import=None):
    """Planned cost — BCWS, the Planned Value of earned-value analysis:
    sum(schedule_percent x budgeted_cost) across the batch's activities.

    Where `project_earned_progress` says what the money has bought, this says
    what the BASELINE expected to have been spent by the data date. It is
    per-activity by construction: the budget is time-phased over each row's own
    baseline percentage and only then summed, so a front-loaded programme reads
    differently from a flat one over the same dates.

    `None` when no activity carries both columns — a zone tracker imports
    neither, and a source with budgets but no baseline percentage has no plan
    to cost. Verified against the Cairo Airport export: 619,638,112.21 of a
    656,013,770.47 budget."""
    total = sum(cost for _sid, cost, _budget in _planned_cost_rows(project, schedule_import))
    return total if total else None


def scope_planned_cost_map(project, schedule_import=None):
    """{scope_id -> planned cost over that scope's whole subtree}, or None when
    the batch has nothing to cost — same rule as project_planned_cost, one
    level down, and the same tree walk every other roll-up here uses."""
    direct = {}
    for sid, cost, _budget in _planned_cost_rows(project, schedule_import):
        direct[sid] = direct.get(sid, 0.0) + cost
    if not direct:
        return None

    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    scopes = (project.scopes.filter(schedule_import=schedule_import)
              if schedule_import else project.scopes.all())
    children, all_ids, roots = {}, [], []
    for sid, pid in scopes.values_list("id", "parent_id"):
        all_ids.append(sid)
        (roots if pid is None else children.setdefault(pid, [])).append(sid)

    sub = {}

    def agg(sid):
        total = direct.get(sid, 0.0)
        for child in children.get(sid, []):
            total += agg(child)
        sub[sid] = total
        return total

    for r in roots:
        agg(r)
    return {str(sid): sub.get(sid, 0.0) for sid in all_ids}


def project_planned_progress(project, schedule_import=None):
    """Planned progress: planned cost / budget, over the same activities.

    The share of the money the BASELINE expected to have been earned by the
    data date — the counterpart to project_earned_progress, and directly
    comparable to it because both divide by the same budget.

    Divided over only the rows planned cost is defined for (see
    _planned_cost_rows), never the project's whole budget: including rows the
    baseline says nothing about would quietly deflate the plan by their budget.

    `None` when there is no baseline to cost. Verified against the Cairo
    Airport export: 619,638,112.21 / 656,013,770.47 = 94.4550%, where the file
    states its own Schedule % Complete as 94.45."""
    cost = base = 0.0
    for _sid, c, b in _planned_cost_rows(project, schedule_import):
        cost += c
        base += b
    return cost / base * 100 if base else None


def scope_planned_progress_map(project, schedule_import=None):
    """{scope_id -> planned progress over that scope's whole subtree}, or None
    when the batch has no baseline to cost — the same tree walk and the same
    "cost over its own base" rule as project_planned_progress."""
    direct_cost, direct_base = {}, {}
    for sid, c, b in _planned_cost_rows(project, schedule_import):
        direct_cost[sid] = direct_cost.get(sid, 0.0) + c
        direct_base[sid] = direct_base.get(sid, 0.0) + b
    if not direct_base:
        return None

    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    scopes = (project.scopes.filter(schedule_import=schedule_import)
              if schedule_import else project.scopes.all())
    children, all_ids, roots = {}, [], []
    for sid, pid in scopes.values_list("id", "parent_id"):
        all_ids.append(sid)
        (roots if pid is None else children.setdefault(pid, [])).append(sid)

    sub_cost, sub_base = {}, {}

    def agg(sid):
        c, b = direct_cost.get(sid, 0.0), direct_base.get(sid, 0.0)
        for child in children.get(sid, []):
            cc, cb = agg(child)
            c += cc
            b += cb
        sub_cost[sid], sub_base[sid] = c, b
        return c, b

    for r in roots:
        agg(r)

    # No entry for a scope whose subtree carried none of the baseline — its
    # callers fall back to their own date estimate, exactly as before.
    return {str(sid): sub_cost[sid] / sub_base[sid] * 100
            for sid in all_ids if sub_base.get(sid)}


def project_earned_progress(project, schedule_import=None):
    """Actual progress as EARNED VALUE: sum(earned_value_cost) / sum(budgeted_cost).

    This is what a P6 export means by "Performance % Complete" — P6 derives
    earned value as that percentage times the activity's budget, so dividing
    back out recovers it exactly, whatever earned-value technique the planner
    configured on the WBS. Verified against the Cairo Airport export: the
    file states 0.5955 and these sums give 59.5489.

    Summed, NOT averaged per activity: a cost-weighted mean of each row's own
    EV/BAC collapses to exactly this ratio, so a scope, a phase and the whole
    project all agree by construction rather than by coincidence. Rows with a
    zero budget (milestones, level-of-effort) contribute nothing to either
    sum and drop out on their own.

    `None` — not 0.0 — when the batch carries no cost columns at all, which is
    every zone-tracker import: those fields are null by design, and callers
    fall back to the weight-based roll-up rather than reporting a project as
    having made no progress.
    """
    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    activities = (project.activities.filter(schedule_import=schedule_import)
                  if schedule_import else project.activities.all())
    agg = activities.exclude(budgeted_cost=None).aggregate(
        bac=Sum("budgeted_cost"), ev=Sum("earned_value_cost"))
    bac = agg["bac"] or 0
    if not bac:
        return None
    return float((agg["ev"] or 0) / bac * 100)


def scope_earned_progress_map(project, schedule_import=None):
    """{scope_id -> EV/BAC over that scope's whole subtree}, or None when the
    batch carries no cost at all — same rule and same reasoning as
    project_earned_progress, one level down.

    A scope whose subtree holds only zero-budget rows has no meaningful
    percentage, so it is left at 0.0 rather than dividing by zero."""
    if schedule_import is None:
        schedule_import = latest_schedule_import(project)
    activities = (project.activities.filter(schedule_import=schedule_import)
                  if schedule_import else project.activities.all())
    direct_bac, direct_ev = {}, {}
    seen_cost = False
    for sid, bac, ev in activities.exclude(budgeted_cost=None).values_list(
            "scope_id", "budgeted_cost", "earned_value_cost"):
        seen_cost = True
        direct_bac[sid] = direct_bac.get(sid, 0.0) + float(bac)
        direct_ev[sid] = direct_ev.get(sid, 0.0) + float(ev or 0)
    if not seen_cost:
        return None

    scopes = (project.scopes.filter(schedule_import=schedule_import)
              if schedule_import else project.scopes.all())
    children, all_ids, roots = {}, [], []
    for sid, pid in scopes.values_list("id", "parent_id"):
        all_ids.append(sid)
        (roots if pid is None else children.setdefault(pid, [])).append(sid)

    sub_bac, sub_ev = {}, {}

    def agg(sid):
        b, e = direct_bac.get(sid, 0.0), direct_ev.get(sid, 0.0)
        for child in children.get(sid, []):
            cb, ce = agg(child)
            b += cb
            e += ce
        sub_bac[sid], sub_ev[sid] = b, e
        return b, e

    for r in roots:
        agg(r)

    return {str(sid): (sub_ev[sid] / sub_bac[sid] * 100 if sub_bac.get(sid) else 0.0)
            for sid in all_ids}


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
    derived from the project's dates, so editing them updates the baseline too.

    A project whose dashboard workbook supplied its own progress curve uses
    THAT instead, exactly as the report's S-curve does — the client asked for
    the Overview chart and the S-curve to tell the same story (2026-09-09).
    It is the curve they publish, so anything derived here could only
    contradict it. Months the curve leaves without an actual reading are left
    out rather than drawn as zero."""
    from django.utils import timezone

    from .models import ProgressEntry

    curve = list(project.curve_points.order_by("date")
                 .values("date", "early_planned", "actual"))
    if curve:
        return [
            {"date": c["date"],
             "overall_progress": round(float(c["actual"]), 1),
             "planned": (round(float(c["early_planned"]), 1)
                         if c["early_planned"] is not None else None)}
            for c in curve if c["actual"] is not None
        ][-max_points:]

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
    # Planned cost over its own budget wherever the schedule carries cost, so
    # every level matches the project headline and neither figure depends on
    # which basis _weight_key happened to pick for this file.
    planned = scope_planned_progress_map(project, schedule_import)
    if planned is not None:
        return planned
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
    # Same rule as project_overall_progress: earned value where the schedule
    # has cost, so every level of the tree agrees with the project headline.
    earned = scope_earned_progress_map(project, schedule_import)
    if earned is not None:
        return earned
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
