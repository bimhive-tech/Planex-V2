"""Report data assembly — gathers the real project numbers the PDF renders.
We only include data we actually have; missing fields are simply omitted."""
from apps.projects.models import ProjectScope
from apps.projects.services import project_overall_progress, scope_progress_map


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
    return [{"name": name, "progress": progress.get(str(sid), 0.0)} for sid, name in zones]


def build_report_context(report):
    """Assemble the full data dict the PDF generator consumes."""
    project = report.project
    overall = project_overall_progress(project)
    breakdown = _breakdown(project)

    milestones = list(
        project.milestones.order_by("sort_order", "date").values("title", "date", "status")
    )
    snapshots = list(
        project.snapshots.order_by("date").values("date", "overall_progress", "source")
    )

    return {
        "report": {
            "title": report.title,
            "number": report.report_number,
            "period_start": report.period_start,
            "period_finish": report.period_finish,
            "status": report.get_status_display(),
        },
        "project": {
            "name": project.name,
            "code": project.code,
            "type": project.get_project_type_display(),
            "location": project.location,
            "description": project.description,
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
        "breakdown": breakdown,
        "zones": _zone_rows(project),
        "milestones": milestones,
        "snapshots": snapshots,
    }
