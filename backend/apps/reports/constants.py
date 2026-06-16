"""Default report-template config. Every styling/layout knob the builder exposes
lives here so the PDF generator and the UI share one source of truth.

Defaults reproduce the look of the reference monthly construction report:
full page border, boxed header (logo | project | logo) + report-line, blue
underlined section headings, bordered info table, and planned/actual charts."""
import copy

DEFAULT_CONFIG = {
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
        "cover_bg": "#ffffff",
        "cover_accent": "#963634",       # maroon bar + project title on the cover
        "chart_planned": "#2E74B5",
        "chart_actual": "#C0504D",
    },
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
        "progress_chart": True,
        "zone_progress": True,
        "milestones": True,
        "timeline": True,
        "notes": True,
        "photos": True,
    },
    "table": {"header_bold": True, "zebra": True, "border": True},
    # Every visible heading/column/field label — editable so a template can be
    # fully Arabic, fully English, or anything between ("control everything").
    "labels": {
        "summary": "Executive Summary",
        "project_info": "Project Information",
        "description": "Project Description",
        "progress_overview": "Overall Progress",
        "progress_chart": "Planned vs Actual",
        "zone_progress": "Progress by Zone",
        "milestones": "Key Milestones",
        "timeline": "Progress Timeline",
        "notes": "Notes",
        "photos": "Site Photos",
        "col_zone": "Zone",
        "col_progress": "Progress",
        "col_milestone": "Milestone",
        "col_date": "Date",
        "col_status": "Status",
        "col_source": "Source",
        "overall_complete": "Complete",
        "completed": "Completed",
        "in_progress": "In Progress",
        "not_started": "Not Started",
        "activities": "activities",
        "planned": "Planned",
        "actual": "Actual",
        # Project-info row labels.
        "info_name": "Project name",
        "info_client": "Owner / Client",
        "info_consultant": "Consultant",
        "info_contractor": "Contractor",
        "info_type": "Type",
        "info_location": "Location",
        "info_budget": "Project value",
        "info_start": "Project start",
        "info_finish": "Contractual finish",
        "info_size": "Built-up area (m²)",
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
