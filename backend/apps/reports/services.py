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
    """Count activities by progress bucket for the summary bars."""
    total = completed = in_progress = not_started = 0
    for (p,) in project.activities.values_list("progress_percent"):
        total += 1
        p = float(p)
        if p >= 100:
            completed += 1
        elif p <= 0:
            not_started += 1
        else:
            in_progress += 1
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
    }


def _zone_rows(project):
    """Top-level zones with rolled-up progress, sorted by tree order."""
    progress = scope_progress_map(project)
    zones = (
        ProjectScope.objects.filter(
            project=project, parent__isnull=True, scope_type=ProjectScope.ScopeType.ZONE
        )
        .order_by("sort_order", "name")
        .values_list("id", "name")
    )
    return [{"id": str(sid), "name": name, "progress": progress.get(str(sid), 0.0)} for sid, name in zones]


def _zone_details(project, zone_ids):
    """Per-zone breakdown: the zone's direct children (phases) with rolled-up
    progress — the report's 'units' tables, not every BOQ leaf."""
    progress = scope_progress_map(project)
    children, names, orders = {}, {}, {}
    for sid, pid, name, so in project.scopes.values_list("id", "parent_id", "name", "sort_order"):
        children.setdefault(str(pid), []).append(str(sid))
        names[str(sid)] = name
        orders[str(sid)] = so

    details = []
    for zid in zone_ids:
        kids = sorted(children.get(zid, []), key=lambda c: (orders.get(c, 0), names.get(c, "")))
        rows = [(names[c], progress.get(c, 0.0)) for c in kids]
        if rows:
            details.append({"zone_id": zid, "rows": rows})
    return details


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

    zones = _zone_rows(project)
    for z in zones:
        z["previous"] = prev_zone.get(z["name"])
        z["planned"] = planned  # time-based baseline is project-wide

    # Scope filter: limit the report to chosen zones (empty = whole project).
    scope_ids = [str(s) for s in (report.scope_ids or [])]
    if scope_ids:
        zones = [z for z in zones if z["id"] in scope_ids]
    name_by_id = {z["id"]: z["name"] for z in zones}
    zone_details = _zone_details(project, [z["id"] for z in zones])
    for d in zone_details:
        d["zone_name"] = name_by_id.get(d["zone_id"], "")

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
        "zone_details": zone_details,
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
