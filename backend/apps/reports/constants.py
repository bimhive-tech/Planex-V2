"""Default report-template config. Every styling/layout knob the builder exposes
lives here so the PDF generator and the UI share one source of truth.

Defaults reproduce the look of the reference monthly construction report:
full page border, boxed header (logo | project | logo) + report-line, blue
underlined section headings, bordered info table, and planned/actual charts."""
import copy

DEFAULT_CONFIG = {
    # "auto" guesses Arabic/English from the project name and labels (the old,
    # implicit behavior — kept as the default so existing templates render
    # unchanged); "ar"/"en" pin it explicitly instead of guessing.
    "language": "auto",
    "page": {"size": "A4", "orientation": "portrait", "margin_mm": 16},
    "colors": {
        "primary": "#1F4E79",
        "heading": "#1F4E79",
        "section_heading": "#1F4E79",   # blue underlined section titles
        "toc_title": "#2E74B5",
        "text": "#1e2430",
        "muted": "#595959",
        "page_border": "#000000",       # thin box around every page
        "header_border": "#000000",
        "table_header_bg": "#1F4E79",
        "table_header_text": "#ffffff",
        "table_border": "#000000",
        "table_row_alt": "#eef3f8",
        "table_highlight": "#FFF2CC",    # info-table rows worth flagging (forecast/delay dates) — see _info_table
        "cover_bg": "#ffffff",
        "cover_accent": "#963634",       # maroon bar + project title on the cover
        "chart_planned": "#4F81BD",      # sampled from the reference dashboard's own
        "chart_actual": "#C0504D",       # bar/pie/line charts — its dominant blue/red pair
        "chart_grid": "#D9D9D9",         # faint horizontal gridlines behind bars/lines
        # Cycled by index for a chart with more than 2 data series (the
        # submittals/shop-drawing stacked-by-discipline bars, the 4-line
        # progress curve) — the same Office 2007 Accent1-6 theme
        # chart_planned/chart_actual (Accent1/2) already sample from, so an
        # N-series chart stays visually consistent with the 2-series ones.
        "chart_palette": ["#4F81BD", "#C0504D", "#9BBB59", "#8064A2", "#4BACC6", "#F79646"],
        "gauge_bad": "#B40000",          # SPI/completion gauge bands — 4 zones,
        "gauge_warn": "#FFC000",         # colors sampled from the reference dashboard's
        "gauge_good": "#FFFF00",         # own speedometer chart (Poor/Average/Good/Excellent)
        "gauge_excellent": "#77933C",
    },
    # SPI/completion gauge band cutoffs, in percent (0-100): below `low` is
    # gauge_bad, low-mid is gauge_warn, mid-high is gauge_good, above `high`
    # is gauge_excellent.
    "gauge_thresholds": {"low": 50, "mid": 70, "high": 90},
    "fonts": {
        "base_size": 11,
        "h1_size": 22,
        "h2_size": 16,
        "h3_size": 13,
        "cover_title_size": 22,
        "line_spacing": 1.5,
    },
    "cover": {
        "enabled": True,
        "title": "Monthly Progress Report",
        "subtitle": "",
        "prepared_by": "Prepared by",
        "org": "",
        "show_logo": True,
        "show_overall": True,
    },
    "toc": {"enabled": True, "title": "Table of Contents"},
    # Word-like formatting for the description text block.
    "description": {
        "align": "auto",        # auto | right | left | center
        "size": 11,
        "color": "#1e2430",
        "bold": False,
        "underline": False,
        "bullets": True,
    },
    "header": {
        "enabled": True,
        "show_project": True,
        "show_report_no": True,
        "org_left": "",
        "org_right": "",
    },
    "footer": {"enabled": True, "show_page_number": True, "text": ""},
    "page_border": {"enabled": True},
    "sections": {
        "summary": True,
        "project_info": True,
        "description": True,
        "progress_overview": True,
        "dashboard": True,
        "progress_chart": True,
        "area_progress_chart": False,  # optional: planned/actual bars one level below zones
        "duration": True,
        "scurve": True,
        "progress_compare": True,
        "zone_progress": True,
        "hierarchy_progress": True,
        "discipline_progress": True,
        "area_dashboards": True,
        "gantt_schedule": True,
        "cashflow": True,
        "invoices": True,
        "submittals": True,
        "detailed_progress": True,
        "delays": True,
        "milestones": True,
        "timeline": True,
        "notes": True,
        "photos": True,
        "attachments": True,
    },
    "table": {"header_bold": True, "zebra": True, "border": True},
    # Insert a blank "section divider" page (centered heading) before each major
    # section, like the reference report.
    "dividers": False,
    # Every visible heading/column/field label — editable so a template can be
    # fully Arabic, fully English, or anything between ("control everything").
    "labels": {
        "summary": "Executive Summary",
        "project_info": "Project Information",
        "description": "Project Description",
        "progress_overview": "Overall Progress",
        "progress_chart": "Planned vs Actual",
        "area_progress_chart": "Planned vs Actual by Area",
        "zone_progress": "Progress by Zone",
        "area_progress": "الإنجاز حسب المنطقة",
        "duration": "المدة الزمنية",
        "item.children": "المناطق الفرعية",
        "item.duration": "المدة الزمنية",
        "item.units": "الإنجاز حسب الوحدة",
        "breakdown": "توزيع الإنجاز",
        "custom": "جدول مخصص",
        "gantt": "الجدول الزمني",
        "submittals_material": "موقف المواد حسب التخصص",
        "submittals_shop_drawing": "موقف الرسومات التنفيذية حسب التخصص",
        "hierarchy_progress": "تفصيل نسب الإنجاز",
        "discipline_progress": "الإنجاز حسب التخصص",
        "area_dashboards": "لوحات معلومات المناطق",
        "gantt_schedule": "الجدول الزمني للمشروع",
        "gantt_revised": "النهاية المعدلة",
        "cashflow": "التدفق النقدي",
        "cashflow_monthly": "التدفق النقدي الشهري",
        "cashflow_cumulative": "التدفق النقدي التراكمي",
        # The four series the combined cash-flow panel draws (monthly bars +
        # cumulative lines), mirroring the reference report's own legend.
        "cashflow_planned_monthly": "المخطط الشهري",
        "cashflow_actual_monthly": "الفعلي الشهري",
        "cashflow_cum_planned": "التراكمي المخطط",
        "cashflow_cum_actual": "التراكمي الفعلي",
        "invoices": "المستخلصات",
        "invoice_status": "موقف المستخلصات",
        "invoice_invoiced": "المصروف",
        "invoice_remaining": "المتبقي",
        "budget_total_cost": "التكلفة الإجمالية للميزانية",
        "budget_contract": "قيمة العقد",
        "budget_new_items": "أعمال إضافية",
        "budget_for_part": "قيمة الجزء",
        "boq_financial_progress": "التقدم المالي حسب جدول الكميات",
        "progress_comparison": "مقارنة نسب الإنجاز",
        "progress_tracking": "متابعة الإنجاز الشهري",
        "tracking_previous": "الشهر السابق",
        "tracking_current": "الشهر الحالي",
        "budget_share": "نسبة الميزانية",
        "financial_percent": "نسبة الإنجاز المالي",
        "submittals": "موقف الرسومات والمواد",
        "submittal_summary": "ملخص الحالة",
        "col_invoice": "البيان",
        "col_value": "القيمة",
        "col_total": "الإجمالي",
        "col_type": "النوع",
        "col_discipline": "التخصص",
        "col_reference": "المرجع",
        "col_count": "العدد",
        # Arabic for the model enums that reach the page as data (milestone
        # status, submittal type/discipline/status). The models keep English
        # display labels because the UI and API use them; a fully-Arabic
        # report translates them here instead, which is what
        # `labels` is for — otherwise ~320 English values print inside an
        # otherwise all-Arabic document (2026-08-30). Keyed by the model's own
        # English label, so an untranslated one simply falls through unchanged.
        "enum_completed": "مكتمل",
        "enum_in_progress": "قيد التنفيذ",
        "enum_upcoming": "قادم",
        "enum_open": "مفتوح",
        "enum_resolved": "تم الحل",
        "enum_pending": "قيد الانتظار",
        "enum_approved": "معتمد",
        "enum_approved_with_comments": "معتمد مع ملاحظات",
        "enum_rejected": "مرفوض",
        "enum_under_review": "قيد المراجعة",
        "enum_shop_drawing": "رسومات تنفيذية",
        "enum_material": "مواد",
        "enum_concrete": "خرسانة",
        "enum_architecture": "معماري",
        "enum_electrical": "كهرباء",
        "enum_mechanical": "ميكانيكا",
        "enum_other": "أخرى",
        "enum_residential": "سكني",
        # Item-scoped chart sources (a repeating page's own zone/phase). Without
        # these, a title/caption falls back to the raw source key and prints
        # "item.spi" on the page (2026-08-30).
        "item.spi": "مؤشر الأداء الزمني",
        "item.duration": "المدة الزمنية",
        "item.units": "الإنجاز حسب الوحدة",
        "item.children": "تفاصيل الوحدات",
        # The reference report's own "Progress Sheet" columns (its page 32).
        "progress_sheet": "ورقة متابعة الإنجاز",
        "col_actual_this": "الفعلي التراكمي (هذا الشهر)",
        "col_this_month": "إنجاز هذا الشهر",
        "col_performance_factor": "معامل الأداء",
        "col_variance": "الانحراف",
        "col_unit": "الوحدة",
        "col_concrete": "الخرسانة",
        "col_architecture": "المعماري",
        "col_electrical": "الكهرباء",
        "col_mechanical": "الميكانيكا",
        "col_other": "أخرى",
        "milestones": "Key Milestones",
        "timeline": "Progress Timeline",
        "notes": "Notes",
        "photos": "Site Photos",
        "attachments": "Attachments",
        "col_zone": "Zone",
        "col_progress": "Progress",
        "col_milestone": "Milestone",
        "col_date": "التاريخ",
        "col_status": "الحالة",
        "col_source": "Source",
        "overall_complete": "Complete",
        "completed": "Completed",
        "in_progress": "In Progress",
        "not_started": "Not Started",
        "activities": "activities",
        "planned": "Planned",
        "actual": "Actual",
        "dashboard": "Executive Dashboard",
        "progress_report": "Project Progress Report",
        "duration_section": "Duration & Delay",
        "duration_days": "Project duration",
        "delay_days": "Delay (days)",
        # Arabic like the rest of this dict — these three now print on the
        # duration pie itself (not just the legacy duration table), and the
        # reference report they mirror is entirely Arabic.
        "duration_total": "مدة المرحلة",
        "duration_elapsed": "المنقضية",
        "duration_remaining": "المتبقية",
        # Planned - actual, the reference PROGRESS pie's own third slice.
        "variance": "الانحراف",
        # The forecast run-out on the progress curve (actual -> 100%).
        "scurve_forecast": "المتوقع",
        # Unit words appended to bare numbers so a reader knows what they mean.
        "unit_days": "days",
        "unit_sqm": "m²",
        "scurve": "Time Performance",
        "spi": "SPI",
        "gauge_poor": "Poor",
        "gauge_average": "Average",
        "gauge_good": "Good",
        "gauge_excellent": "Excellent",
        "progress_compare": "Progress vs Plan",
        # "illustration", not "figure" — matches the client's own real
        # reference report's caption wording exactly ("رسم توضيحي1- ...").
        "figure": "رسم توضيحي",
        "table_caption": "جدول",
        "image_caption": "صورة",
        "col_previous": "Previous %",
        "col_planned": "Planned %",
        "col_actual": "Actual %",
        "divider": "Section",
        "detailed_progress": "Detailed Progress",
        "col_task": "Task",
        "critical_path_delays": "المسار الحرج للتأخيرات",
        "col_forecast_finish": "النهاية المتوقعة",
        "activity_schedule": "Activity Schedule Detail",
        "col_bl_duration": "BL Duration",
        "col_original_duration": "Original Duration",
        "col_actual_duration": "Actual Duration",
        "col_remaining_duration": "Remaining Duration",
        "col_spi": "SPI",
        "col_schedule_variance": "Schedule Variance",
        "delays": "Obstacles & Delays",
        "col_delay": "Obstacle / Delay",
        "col_impact": "Impact (days)",
        "status_open": "قائم",
        "status_resolved": "تم الحل",
        # Project-info row labels.
        "info_name": "Project name",
        "info_client": "Owner / Client",
        "info_consultant": "Consultant",
        "info_contractor": "Contractor",
        "info_type": "Type",
        "info_location": "Location",
        "info_budget": "Project value",
        "info_code": "Project code",
        "info_start": "Project start",
        "info_finish": "Contractual finish",
        # revised_finish (the baseline as last revised) and forecast_finish
        # (the current best-guess completion date) are two distinct project
        # fields — keep their rows and labels separate rather than
        # collapsing them into one, as the legacy "Forecast finish" label
        # here used to do while actually reading revised_finish.
        "info_revised": "Revised finish",
        "info_forecast": "Forecast finish",
        "info_duration": "Contract duration (days)",
        "info_delay": "Delay (days)",
        "info_size": "Built-up area (m²)",
        "info_contract_value": "Contract value",
        "info_approved_value": "Approved value",
        "info_forecast_cost": "Forecast cost",
        "info_progress_as_on": "Progress as on",
        "info_contractor_consultant": "Contractor's Consultant",
        "info_advance_payment": "Advance Payment",
        "info_eot": "EOT (Days)",
        "info_part_amount": "(Part) Amount",
        "info_part_completion_revised": "(Part) Completion Date (Revised Baseline)",
        "info_part_forecast": "(Part) Forecasted Completion Date",
        "info_part_delay": "(Part) Delay (Calendar Days)",
    },
}


def default_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def merged_config(config):
    """Deep-merge a stored (possibly partial) config over the defaults so older
    templates still render when new knobs are added."""
    base = default_config()

    def merge(dst, src):
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(base, config or {})
    return base


def apply_report_layout_override(cfg: dict, report) -> dict:
    """A report can diverge from its template's pages/content without
    touching the template (Report.layout_override, set once the report's own
    "Customize this report" editor is saved). Colors, fonts, and labels stay
    whatever the template says either way. layout.pages is a full swap (a
    report's pages are independently edited once customized at all).
    page_design is merged key-by-key rather than swapped wholesale — the
    Customize tab only ever lets a report override master_elements (its own
    header/footer content), never margins/page size/etc., so those keep
    tracking the template live even after a report has its own header."""
    return merge_layout_override(cfg, getattr(report, "layout_override", None))


def merge_layout_override(cfg: dict, override: dict | None) -> dict:
    """Same merge apply_report_layout_override does, but against an explicit
    override dict rather than the report's saved one — lets the Customize
    tab's live chart/table previews (see chart_svgs/table_data) render an
    unsaved draft without writing anything to the DB first."""
    if not override:
        return cfg
    cfg = copy.deepcopy(cfg)
    if override.get("page_design"):
        cfg["page_design"] = {**(cfg.get("page_design") or {}), **override["page_design"]}
    if override.get("layout"):
        cfg["layout"] = override["layout"]
    return cfg
