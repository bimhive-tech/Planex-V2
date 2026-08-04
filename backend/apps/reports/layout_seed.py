"""Seeds a Page Designer / Report Configuration canvas layout from a
template's existing Content & Labels config (sections/labels/header/footer/
cover) — a starting point for templates authored before the canvas engine
existed, not a pixel-perfect conversion. The bespoke cover composition and
the executive dashboard's nested-panel layout are the two spots most likely
to need a manual tidy-up pass after seeding (see the project plan). Sections
with no canvas equivalent yet (rich-text description/notes, timeline, TOC)
are skipped rather than approximated badly.
"""
import uuid

from .pdf_canvas import PAGE_SIZES_MM

HEADER_MM = 30
FOOTER_MM = 14
HEADING_H = 12
GAP_MM = 4

# Pie/donut charts (pdf_charts._duration_pie_for/overall_donut) fix their pie
# near the bottom of whatever box they're given and their legend near the
# top — fine at their natural ~60mm size, but handed a much taller box (as a
# full-height content area often is) the two visibly separate with a large
# gap between them. Capping their box near the natural size keeps them
# looking like a chart instead of two disconnected pieces.
PIE_MAX_H = 65


def _new_id():
    return str(uuid.uuid4())


def _page_wh(page_cfg):
    w, h = PAGE_SIZES_MM.get(page_cfg.get("size", "A4"), PAGE_SIZES_MM["A4"])
    if page_cfg.get("orientation") == "landscape":
        w, h = h, w
    return w, h


def _el(type_, x, y, w, h, props, z=0):
    return {"id": _new_id(), "type": type_, "x": round(x, 1), "y": round(y, 1),
            "w": round(w, 1), "h": round(h, 1), "z": z, "props": props}


def _page(name, elements):
    return {"id": _new_id(), "name": name, "elements": elements}


def _content_box(design):
    w, h = _page_wh({"size": design["size"], "orientation": design["orientation"]})
    margin = design["margin_mm"]
    top = margin + (design["header_mm"] if design["show_header"] else 0)
    bottom = margin + (design["footer_mm"] if design["show_footer"] else 0)
    return {"x": margin, "y": top, "w": max(0, w - margin * 2), "h": max(0, h - top - bottom)}


def _below_heading(box):
    return {"x": box["x"], "y": box["y"] + HEADING_H + GAP_MM, "w": box["w"],
            "h": max(0, box["h"] - HEADING_H - GAP_MM)}


def _heading_el(cfg, text, box):
    """Section heading + its underline rule — the "blue underlined section
    titles" look the legacy Content & Labels renderer always had (HRFlowable
    under every _heading() call) but the canvas seeder skipped, drawing the
    text alone. Returns a list so callers spread it: `[*_heading_el(...), ...]`."""
    color = cfg["colors"].get("section_heading", "#1F4E79")
    text_el = _el("text", box["x"], box["y"], box["w"], HEADING_H,
                  {"text": text, "size": cfg["fonts"].get("h2_size", 16), "bold": True,
                   "align": "center", "color": color})
    rule_w = box["w"] * 0.4
    rule = _el("line", box["x"] + (box["w"] - rule_w) / 2, box["y"] + HEADING_H - 1, rule_w, 1.2,
               {"stroke": color, "stroke_width": 0.5})
    return [text_el, rule]


def _panel(x, y, w, h, cfg, z=5):
    """A thin outline framing a chart/table quadrant — the boxed-panel look
    the reference report uses throughout (and the legacy Content & Labels
    renderer never needed, since Platypus tables/frames draw their own
    borders). Stroke-only and drawn on top (high z) so it never has to worry
    about covering the chart underneath — there's nothing to cover."""
    return _el("rect", x, y, w, h, {"stroke": cfg["colors"].get("table_border", "#d9d9d9"),
                                     "stroke_width": 0.3}, z=z)


def _chart_props(cfg, source, chart_type):
    return {"source": source, "chart_type": chart_type, "legend": True,
            "color_a": cfg["colors"].get("chart_planned", "#2E74B5"),
            "color_b": cfg["colors"].get("chart_actual", "#C0504D")}


def _table_props(cfg, source):
    return {"source": source, "zebra": True, "border": True,
            "header_bg": cfg["colors"].get("table_header_bg", "#1F4E79"),
            "header_text": cfg["colors"].get("table_header_text", "#ffffff")}


def _master_elements(cfg, w, h, margin):
    header = cfg.get("header", {})
    footer = cfg.get("footer", {})
    colors = cfg.get("colors", {})
    content_w = w - 2 * margin
    els = []

    if header.get("enabled", True):
        left_w, right_w = content_w * 0.28, content_w * 0.24
        center_w = content_w - left_w - right_w
        top_h = HEADER_MM * 0.65
        els.append(_el("logo", margin + 2, margin + 2, left_w - 4, top_h - 4, {"source": "left"}))
        els.append(_el("logo", margin + left_w + center_w + 2, margin + 2, right_w - 4, top_h - 4,
                        {"source": "right"}))
        if header.get("show_project", True):
            els.append(_el("field", margin + left_w, margin, center_w, top_h,
                            {"source": "project.name", "size": 12, "bold": True, "align": "center",
                             "color": colors.get("heading", "#1F4E79")}))
        if header.get("show_report_no", True):
            sub_y, sub_h = margin + top_h, HEADER_MM - top_h
            els.append(_el("field", margin, sub_y, content_w * 0.5, sub_h,
                            {"source": "report.title", "size": 9, "align": "center",
                             "color": colors.get("text", "#1e2430")}))
            els.append(_el("field", margin + content_w * 0.5, sub_y, content_w * 0.5, sub_h,
                            {"source": "report.period", "size": 9, "align": "center",
                             "color": colors.get("text", "#1e2430")}))

    if footer.get("enabled", True) and footer.get("show_page_number", True):
        fy = h - margin - FOOTER_MM + 2
        els.append(_el("field", margin, fy, content_w, FOOTER_MM - 4,
                        {"source": "page.number", "size": 9, "align": "center",
                         "color": colors.get("muted", "#595959")}))
    return els


def _cover_page(cfg, w, h, margin):
    """Approximates the reference cover: logo, a bordered cover image, the
    maroon accent bar + tick near the right edge (drawn in Python on the
    legacy cover — here as real rect elements so it's editable), title,
    prepared-by."""
    cover, colors = cfg.get("cover", {}), cfg.get("colors", {})
    accent = colors.get("cover_accent", "#963634")
    els = []
    if cover.get("show_logo", True):
        els.append(_el("logo", margin + 6, margin + 6, 48, 22, {"source": "left"}))

    bar_w, bar_h_frac, bar_y_frac = 1.4, 0.44, 0.28
    bar_x = w - margin - 6 - bar_w
    bar_y = h - bar_y_frac * h - bar_h_frac * h
    els.append(_el("rect", bar_x, bar_y, bar_w, bar_h_frac * h, {"fill": accent}))
    tick_w, tick_h = 12, 1.4
    els.append(_el("rect", bar_x - tick_w, h * 0.50 - tick_h, tick_w, tick_h, {"fill": accent}))

    cover_x, cover_y, cover_h = margin + 6, h * 0.30, h * 0.21
    cover_w = bar_x - cover_x - 6  # leave clearance before the accent bar
    els.append(_el("logo", cover_x, cover_y, cover_w, cover_h, {"source": "cover"}))
    els.append(_el("rect", cover_x, cover_y, cover_w, cover_h,
                    {"stroke": colors.get("table_border", "#000000"), "stroke_width": 0.3}, z=1))
    title = cover.get("title") or ""
    if title:
        els.append(_el("text", margin, h * 0.55, w - 2 * margin, 18,
                        {"text": title, "size": cfg["fonts"].get("cover_title_size", 22), "bold": True,
                         "align": "center", "color": colors.get("cover_accent", "#963634")}))
    if cover.get("prepared_by"):
        els.append(_el("text", margin, h * 0.63, w - 2 * margin, 8,
                        {"text": cover["prepared_by"], "size": 11, "align": "center",
                         "color": colors.get("muted", "#595959")}))
    els.append(_el("field", margin, h * 0.80, w - 2 * margin, 22,
                    {"source": "project.name", "size": cfg["fonts"].get("cover_title_size", 22) + 2,
                     "bold": True, "align": "center", "color": colors.get("cover_accent", "#963634")}))
    return _page("Cover", els)


def _field_page(cfg, design, label_key, source, name, size=16):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get(label_key, label_key), box)
    field = _el("field", sub["x"], sub["y"], sub["w"], min(20, sub["h"]),
                {"source": source, "size": size, "bold": True, "align": "center",
                 "color": cfg["colors"].get("heading", "#1F4E79")})
    return _page(name, [*heading, field])


def _progress_overview_page(cfg, design):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get("progress_overview", "Overall Progress"), box)
    field = _el("field", sub["x"], sub["y"], sub["w"], 12,
                {"source": "progress.overall", "size": 16, "bold": True, "align": "center",
                 "color": cfg["colors"].get("heading", "#1F4E79")})
    chart_y = sub["y"] + 16
    chart_h = min(PIE_MAX_H, max(0, sub["h"] - 16))
    chart = _el("chart", sub["x"], chart_y, sub["w"], chart_h, _chart_props(cfg, "breakdown", "donut"))
    return _page("Overall Progress", [*heading, field, chart])


def _table_page(cfg, design, label_key, source, name):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get(label_key, label_key), box)
    table = _el("table", sub["x"], sub["y"], sub["w"], sub["h"], _table_props(cfg, source))
    return _page(name, [*heading, table])


def _chart_page(cfg, design, label_key, source, chart_type, name):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get(label_key, label_key), box)
    chart = _el("chart", sub["x"], sub["y"], sub["w"], sub["h"], _chart_props(cfg, source, chart_type))
    return _page(name, [*heading, chart])


def _dual_chart_page(cfg, design, label_key, sources, name):
    """Two stacked charts on one page — used for cashflow's monthly + cumulative."""
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get(label_key, label_key), box)
    half_h = (sub["h"] - GAP_MM) / 2
    els = [*heading]
    for i, (source, chart_type) in enumerate(sources):
        y = sub["y"] + i * (half_h + GAP_MM)
        els.append(_el("chart", sub["x"], y, sub["w"], half_h, _chart_props(cfg, source, chart_type)))
        els.append(_panel(sub["x"], y, sub["w"], half_h, cfg))
    return _page(name, els)


def _dashboard_page(cfg, design):
    """Approximates the landscape executive dashboard as a portrait composite
    of 4 charts (donut + duration pie, then zone bars + s-curve) — the
    reference's landscape layout needs a manual pass; the canvas has no
    per-page orientation override yet (see plan gap notes). The project-info
    panel is deliberately left out here: it already gets its own full-width
    page via the "project_info" section, and `_info_table`'s auto-sized value
    column only behaves at full page width — squeezed into a third of this
    page it overflows past the edge (Table.wrap doesn't constrain a `None`
    colWidth to the box, unlike charts which take an explicit width)."""
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get("dashboard", "Executive Dashboard"), box)
    top_h = sub["h"] * 0.45
    bottom_h = max(0, sub["h"] - top_h - GAP_MM)
    half = (sub["w"] - GAP_MM) / 2
    bottom_y = sub["y"] + top_h + GAP_MM
    pie_h = min(PIE_MAX_H, top_h)
    els = [
        *heading,
        _el("chart", sub["x"], sub["y"], half, pie_h, _chart_props(cfg, "breakdown", "donut")),
        _el("chart", sub["x"] + half + GAP_MM, sub["y"], half, pie_h, _chart_props(cfg, "duration", "pie")),
        _el("chart", sub["x"], bottom_y, half, bottom_h, _chart_props(cfg, "zone_progress", "column")),
        _el("chart", sub["x"] + half + GAP_MM, bottom_y, half, bottom_h, _chart_props(cfg, "scurve", "line")),
        _panel(sub["x"], sub["y"], half, pie_h, cfg),
        _panel(sub["x"] + half + GAP_MM, sub["y"], half, pie_h, cfg),
        _panel(sub["x"], bottom_y, half, bottom_h, cfg),
        _panel(sub["x"] + half + GAP_MM, bottom_y, half, bottom_h, cfg),
    ]
    return _page("Executive Dashboard", els)


def _area_dashboard_page(cfg, design):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get("area_dashboards", "Area Dashboards"), box)
    name_field = _el("field", sub["x"], sub["y"], sub["w"], 10,
                      {"source": "item.name", "size": 13, "bold": True, "align": "center",
                       "color": cfg["colors"].get("heading", "#1F4E79")})
    top_y, rest_h = sub["y"] + 12, max(0, sub["h"] - 12)
    top_h = rest_h * 0.55
    bottom_y, bottom_h = top_y + top_h + GAP_MM, max(0, rest_h - top_h - GAP_MM)
    half = (sub["w"] - GAP_MM) / 2
    pie_h = min(PIE_MAX_H, bottom_h)
    els = [
        *heading, name_field,
        _el("chart", sub["x"], top_y, sub["w"], top_h, _chart_props(cfg, "item.units", "bar")),
        _el("chart", sub["x"], bottom_y, half, pie_h, _chart_props(cfg, "item.duration", "pie")),
        _el("table", sub["x"] + half + GAP_MM, bottom_y, half, bottom_h, _table_props(cfg, "item.children")),
        _panel(sub["x"], top_y, sub["w"], top_h, cfg),
        _panel(sub["x"], bottom_y, half, pie_h, cfg),
        _panel(sub["x"] + half + GAP_MM, bottom_y, half, bottom_h, cfg),
    ]
    page = _page("Area Dashboards", els)
    page["repeat"] = {"source": "area_dashboards", "mode": "one_per_item"}
    return page


def _photos_page(cfg, design):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get("photos", "Site Photos"), box)
    cell_w, cell_h = (sub["w"] - GAP_MM) / 2, (sub["h"] - GAP_MM) / 2
    els = [*heading]
    for slot in range(4):
        row, col = divmod(slot, 2)
        x = sub["x"] + col * (cell_w + GAP_MM)
        y = sub["y"] + row * (cell_h + GAP_MM)
        els.append(_el("image", x, y, cell_w, cell_h,
                        {"source": "repeat.item", "slot": slot, "show_caption": True, "fit": "contain"}))
    page = _page("Site Photos", els)
    page["repeat"] = {"source": "photos", "mode": "chunk", "chunk_size": 4}
    return page


def _attachments_page(cfg, design):
    box = _content_box(design)
    sub = _below_heading(box)
    heading = _heading_el(cfg, cfg["labels"].get("attachments", "Attachments"), box)
    image = _el("image", sub["x"], sub["y"], sub["w"], sub["h"],
                {"source": "repeat.item", "slot": 0, "show_caption": True, "fit": "contain"})
    page = _page("Attachments", [*heading, image])
    page["repeat"] = {"source": "attachments", "mode": "chunk", "chunk_size": 1}
    return page


def seed_layout_from_sections(cfg: dict) -> dict:
    """Build {"page_design", "layout": {"pages": [...]}} from a template's
    existing Content & Labels config. A starting point, not a conversion —
    see the module docstring for what's approximated vs. skipped."""
    page_cfg = cfg.get("page", {})
    w, h = _page_wh(page_cfg)
    margin = float(page_cfg.get("margin_mm", 16))
    design = {
        "size": page_cfg.get("size", "A4"),
        "orientation": page_cfg.get("orientation", "portrait"),
        "margin_mm": margin,
        "header_mm": HEADER_MM,
        "footer_mm": FOOTER_MM,
        "show_header": bool(cfg.get("header", {}).get("enabled", True)),
        "show_footer": bool(cfg.get("footer", {}).get("enabled", True)),
        "show_border": bool(cfg.get("page_border", {}).get("enabled", True)),
        "background": "#ffffff",
        "master_elements": _master_elements(cfg, w, h, margin),
    }

    pages = []
    if cfg.get("cover", {}).get("enabled", True):
        pages.append(_cover_page(cfg, w, h, margin))

    sections = cfg.get("sections", {})
    if sections.get("summary"):
        pages.append(_field_page(cfg, design, "summary", "progress.overall", "Executive Summary"))
    if sections.get("project_info"):
        pages.append(_table_page(cfg, design, "project_info", "project_info", "Project Info"))
    if sections.get("dashboard"):
        pages.append(_dashboard_page(cfg, design))
    if sections.get("progress_overview"):
        pages.append(_progress_overview_page(cfg, design))
    if sections.get("progress_chart"):
        pages.append(_chart_page(cfg, design, "progress_chart", "zone_progress", "column", "Planned vs Actual"))
    if sections.get("area_progress_chart"):
        pages.append(_chart_page(cfg, design, "area_progress_chart", "area_progress", "column",
                                  "Planned vs Actual by Area"))
    if sections.get("duration"):
        pages.append(_chart_page(cfg, design, "duration_section", "duration", "pie", "Duration & Delay"))
    if sections.get("scurve"):
        pages.append(_chart_page(cfg, design, "scurve", "scurve", "line", "S-Curve"))
    if sections.get("progress_compare"):
        pages.append(_table_page(cfg, design, "progress_compare", "progress_compare", "Progress vs Plan"))
    if sections.get("zone_progress"):
        pages.append(_table_page(cfg, design, "zone_progress", "zone_progress", "Progress by Zone"))
    if sections.get("hierarchy_progress"):
        pages.append(_table_page(cfg, design, "hierarchy_progress", "hierarchy_progress", "Zone Breakdown"))
    if sections.get("discipline_progress"):
        pages.append(_table_page(cfg, design, "discipline_progress", "discipline_progress", "Progress by Trade"))
    if sections.get("area_dashboards"):
        pages.append(_area_dashboard_page(cfg, design))
    if sections.get("gantt_schedule"):
        pages.append(_chart_page(cfg, design, "gantt_schedule", "gantt", "bar", "Gantt Schedule"))
    if sections.get("cashflow"):
        pages.append(_dual_chart_page(cfg, design, "cashflow",
                                       [("cashflow_monthly", "bar"), ("cashflow_cumulative", "line")], "Cash Flow"))
    if sections.get("invoices"):
        pages.append(_table_page(cfg, design, "invoices", "invoices", "Invoices"))
    if sections.get("submittals"):
        pages.append(_table_page(cfg, design, "submittals", "submittals", "Submittals"))
    if sections.get("detailed_progress"):
        pages.append(_table_page(cfg, design, "detailed_progress", "detailed_progress", "Detailed Progress"))
    if sections.get("delays"):
        pages.append(_table_page(cfg, design, "delays", "delays", "Delays"))
    if sections.get("milestones"):
        pages.append(_table_page(cfg, design, "milestones", "milestones", "Milestones"))
    if sections.get("photos"):
        pages.append(_photos_page(cfg, design))
    if sections.get("attachments"):
        pages.append(_attachments_page(cfg, design))

    if not pages:
        pages.append({"id": _new_id(), "name": "Page 1", "elements": []})

    return {"page_design": design, "layout": {"pages": pages}}
