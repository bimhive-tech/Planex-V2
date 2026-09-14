"""Spread the summary over two pages so every chart on it can be read, and add
the two progress bar charts the planners asked for (register F6, F7).

The summary was one landscape page holding the project-info table and six
charts at 52 mm wide each. At that width the S-curve and the cash flow are a
smear of lines, and two more charts had nowhere to go. It becomes:

  page 1  project info, beside the progress pie, the SPI gauge and both
          submittal charts, each widened to 80 mm
  page 2  the S-curve and the cash flow, then progress by area and progress
          by phase, each 131 mm wide

Only a summary page still holding its original contents is rearranged — the
project-info table and the SPI gauge together identify it — so a summary
someone has since rebuilt by hand is left alone. A layout that already has its
second summary page is skipped, so running this twice never splits page 1
again. Charts that are moved keep their ids and settings; only their position
changes.

Reports carry their layout under "layout" in `layout_override`, the same as a
template's config (see 0011 for what reading it off the top level missed).
"""
import copy
import uuid

from django.db import migrations

_SUMMARY = "الملخص"
_CONTINUED = f"{_SUMMARY} (2)"

# Landscape A4 content, matching the positions the page already uses: the
# info table spans y 36-190 on the left, and charts sit in two rows below the
# heading.
_ROW_Y = (36, 115)
_ROW_H = 75

# Page 1: the right-hand block beside the info table (x 117-281).
_PAGE1 = {
    "breakdown": (201, 0), "spi": (117, 0),
    "submittals_material": (117, 1), "submittals_shop_drawing": (201, 1),
}
_PAGE1_W = 80

# Page 2: the full content width (x 14-281), two columns.
_PAGE2 = (("scurve", 14, 0), ("cashflow_monthly", 150, 0),
          ("zone_progress", 14, 1), ("work_progress", 150, 1))
_PAGE2_W = 131
_CHART_TYPE = {"scurve": "line", "cashflow_monthly": "column",
               "zone_progress": "column", "work_progress": "column"}


def _source(el):
    return (el.get("props") or {}).get("source")


def _is_original_summary(page) -> bool:
    if (page.get("name") or "").strip() != _SUMMARY:
        return False
    sources = {_source(el) for el in page.get("elements") or []}
    return {"project_info", "spi"} <= sources


def _chart(source, x, row):
    return {"id": str(uuid.uuid4()), "type": "chart", "x": x, "y": _ROW_Y[row],
            "w": _PAGE2_W, "h": _ROW_H, "z": 0,
            "props": {"source": source, "chart_type": _CHART_TYPE[source],
                      "show_title": False, "show_caption": True}}


def _split(page):
    """(page 1, page 2) for one original summary page."""
    elements = page.get("elements") or []
    by_source = {_source(el): el for el in elements if _source(el)}
    heading = [el for el in elements if el.get("type") in ("text", "line")]

    first = []
    for el in elements:
        source = _source(el)
        if source in _PAGE1:
            x, row = _PAGE1[source]
            el.update(x=x, y=_ROW_Y[row], w=_PAGE1_W, h=_ROW_H)
            first.append(el)
        elif source not in dict((s, 0) for s, _, _ in _PAGE2):
            first.append(el)            # the heading, the info table, anything else
    page["elements"] = first

    second = []
    for el in heading:                   # the same heading, as its own elements
        clone = copy.deepcopy(el)
        clone["id"] = str(uuid.uuid4())
        second.append(clone)
    for source, x, row in _PAGE2:
        existing = by_source.get(source)
        if existing is not None:
            existing.update(x=x, y=_ROW_Y[row], w=_PAGE2_W, h=_ROW_H)
            second.append(existing)
        else:
            second.append(_chart(source, x, row))

    continued = {k: copy.deepcopy(v) for k, v in page.items() if k not in ("id", "elements", "name")}
    continued.update(id=str(uuid.uuid4()), name=_CONTINUED, elements=second)
    return page, continued


def _rearrange(layout) -> bool:
    pages = (layout or {}).get("pages")
    if not isinstance(pages, list):
        return False
    if any((page.get("name") or "").strip() == _CONTINUED for page in pages):
        return False
    out, changed = [], False
    for page in pages:
        if _is_original_summary(page):
            out.extend(_split(page))
            changed = True
        else:
            out.append(page)
    layout["pages"] = out
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
    dependencies = [("reports", "0011_wording_on_saved_reports")]

    # Irreversible on purpose: merging the pages back would have to guess at
    # positions for charts someone may have moved since.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
