"""Project business logic — progress roll-up from activities."""
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

_WEIGHTED = ExpressionWrapper(
    F("progress_percent") * F("weight"), output_field=DecimalField(max_digits=20, decimal_places=4)
)


def project_overall_progress(project) -> float:
    """Weighted overall progress (0–100): sum(progress*weight)/sum(weight)
    across the project's activities. 0 when there are none."""
    agg = project.activities.aggregate(wsum=Sum("weight"), psum=Sum(_WEIGHTED))
    wsum = agg["wsum"] or 0
    if not wsum:
        return 0.0
    return round(float(agg["psum"] or 0) / float(wsum), 1)


def scope_progress_map(project) -> dict:
    """Map of scope_id -> weighted progress rolled up over the scope's *whole
    subtree*. Computed on the backend so the tree shows real progress without
    shipping every activity (zone trackers have tens of thousands of cells)."""
    direct_w, direct_pw = {}, {}
    for sid, w, p in project.activities.values_list("scope_id", "weight", "progress_percent"):
        w, p = float(w), float(p)
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
