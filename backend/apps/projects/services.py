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
    """Map of scope_id -> weighted progress, rolled up from each scope's own
    activities (direct children). The frontend composes deeper subtree totals."""
    rows = (
        project.activities.values("scope_id")
        .annotate(wsum=Sum("weight"), psum=Sum(_WEIGHTED))
    )
    out = {}
    for r in rows:
        wsum = r["wsum"] or 0
        out[str(r["scope_id"])] = round(float(r["psum"] or 0) / float(wsum), 1) if wsum else 0.0
    return out
