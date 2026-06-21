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
    (an activity_id->% map, e.g. as-of-date) is given, weight against it,
    falling back to each activity's current % for ids absent from the map."""
    if progress is None:
        agg = project.activities.aggregate(wsum=Sum("weight"), psum=Sum(_WEIGHTED))
        wsum = agg["wsum"] or 0
        if not wsum:
            return 0.0
        return round(float(agg["psum"] or 0) / float(wsum), 1)

    wsum = psum = 0.0
    for aid, w, p in project.activities.values_list("id", "weight", "progress_percent"):
        val = progress.get(str(aid), float(p))
        wsum += float(w)
        psum += float(w) * val
    return round(psum / wsum, 1) if wsum else 0.0


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
