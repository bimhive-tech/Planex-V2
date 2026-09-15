"""Register section B on every template and report already saved (planner
review of the Cairo T3 report, 2026-09-14).

B1  The full-width progress-by-area chart comes off the area page.
B2  That page becomes the summary's third page: named "الملخص (3)", headed
    "الملخص" like the other two. Its two remaining charts (progress
    comparison, monthly tracking) keep their size and move up into the space
    the removed chart held.
B3  The time-performance bars come off the project-progress page. The zone
    chart below then takes the freed space: up to just under the charts
    above it and across to the page's right edge, keeping its own bottom
    edge. It only widens when nothing else sits beside it — an older
    template with a chart there is left as it is — and only grows into space
    that is actually empty, so nothing on the page overlaps.

Only a page still holding the charts these steps look for is changed; a page
someone has rebuilt by hand is left alone.
"""
from django.db import migrations

_SUMMARY = "الملخص"
_AREA_PAGE_CHARTS = {"progress_comparison", "progress_tracking"}
_GAP = 4          # mm between charts, as the summary pages use


def _source(el):
    return (el.get("props") or {}).get("source")


def _charts(page, source):
    return [el for el in page.get("elements") or [] if el.get("type") == "chart" and _source(el) == source]


def _is_heading(el):
    return el.get("type") == "text"


# ---------------------------------------------------------------- B1 + B2

def _fold_area_page(page) -> bool:
    elements = page.get("elements") or []
    sources = {_source(el) for el in elements}
    if not _AREA_PAGE_CHARTS <= sources:
        return False
    area = _charts(page, "area_progress")
    if not area:
        return False
    freed_top = min(float(el.get("y") or 0) for el in area)
    kept = [el for el in elements if el not in area]
    rest = [el for el in kept if _source(el) in _AREA_PAGE_CHARTS]
    shift = min(float(el.get("y") or 0) for el in rest) - freed_top
    if shift > 0:
        for el in rest:
            el["y"] = float(el["y"]) - shift
    for el in kept:
        if _is_heading(el):
            el.setdefault("props", {})["text"] = _SUMMARY
    page["elements"] = kept
    page["name"] = f"{_SUMMARY} (3)"
    return True


# ---------------------------------------------------------------- B3

def _overlaps(a, b):
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def _rect(el):
    return (float(el.get("x") or 0), float(el.get("y") or 0), float(el.get("w") or 0), float(el.get("h") or 0))


def _drop_time_performance(page) -> bool:
    removed = _charts(page, "time_performance")
    zones = _charts(page, "zone_progress")
    if not removed or len(zones) != 1:
        return False
    zone = zones[0]
    right_edge = max(el_x + el_w for el_x, _, el_w, _ in (_rect(el) for el in page["elements"]
                                                          if el.get("type") == "chart"))
    page["elements"] = [el for el in page["elements"] if el not in removed]
    others = [_rect(el) for el in page["elements"]
              if el is not zone and el.get("type") in ("chart", "table", "image", "description")]

    x, y, w, h = _rect(zone)
    bottom = y + h
    # Up to just under whatever sits above it.
    above = [oy + oh for ox, oy, ow, oh in others if oy + oh <= y and ox < x + w and x < ox + ow]
    new_y = (max(above) + _GAP) if above else y
    if new_y < y and not any(_overlaps((x, new_y, w, bottom - new_y), o) for o in others):
        y = new_y
    # Across to the right edge, only into empty space.
    new_w = right_edge - x
    if new_w > w and not any(_overlaps((x, y, new_w, bottom - y), o) for o in others):
        w = new_w
    zone.update(x=x, y=y, w=w, h=bottom - y)
    return True


# ---------------------------------------------------------------- apply

def _rearrange(layout) -> bool:
    pages = (layout or {}).get("pages")
    if not isinstance(pages, list):
        return False
    changed = False
    for page in pages:
        changed |= _fold_area_page(page)
        changed |= _drop_time_performance(page)
    return changed


def forwards(apps, schema_editor):
    ReportTemplate = apps.get_model("reports", "ReportTemplate")
    Report = apps.get_model("reports", "Report")

    for template in ReportTemplate.objects.all():
        config = template.config or {}
        if _rearrange(config.get("layout")):
            template.config = config
            template.save(update_fields=["config"])

    for report in Report.objects.exclude(layout_override=None):
        override = report.layout_override or {}
        if _rearrange(override.get("layout")):
            report.layout_override = override
            report.save(update_fields=["layout_override"])


class Migration(migrations.Migration):
    dependencies = [("reports", "0014_duration_pie_replaces_two_charts")]

    # Irreversible on purpose: the removed charts' own settings aren't kept.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
