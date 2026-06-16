"""Default report-template config. Every styling/layout knob the builder exposes
lives here so the PDF generator and the UI share one source of truth."""
import copy

# The full configurable surface: page, colors, fonts, cover, TOC, header/footer,
# section toggles, and table styling. The builder edits a deep copy of this.
DEFAULT_CONFIG = {
    "page": {"size": "A4", "orientation": "portrait", "margin_mm": 18},
    "colors": {
        "primary": "#5b4fe9",
        "heading": "#1e2430",
        "text": "#1e2430",
        "muted": "#6b7280",
        "table_header_bg": "#5b4fe9",
        "table_header_text": "#ffffff",
        "table_border": "#e8eaed",
        "table_row_alt": "#f6f7f9",
        "cover_bg": "#ffffff",
        "cover_accent": "#5b4fe9",
    },
    "fonts": {
        "base_size": 11,
        "h1_size": 22,
        "h2_size": 16,
        "h3_size": 13,
        "cover_title_size": 30,
        "line_spacing": 1.4,
    },
    "cover": {
        "enabled": True,
        "title": "Monthly Progress Report",
        "subtitle": "",
        "show_logo": True,
        "show_overall": True,
    },
    "toc": {"enabled": True, "title": "Table of Contents"},
    "header": {"enabled": True, "show_project": True, "show_report_no": True},
    "footer": {"enabled": True, "show_page_number": True, "text": ""},
    "sections": {
        "summary": True,
        "project_info": True,
        "progress_overview": True,
        "zone_progress": True,
        "milestones": True,
        "timeline": True,
        "notes": True,
    },
    "table": {"header_bold": True, "zebra": True, "border": True},
    # Every visible heading/column label — editable so a template can be fully
    # Arabic, fully English, or anything in between ("control everything").
    "labels": {
        "summary": "Executive Summary",
        "project_info": "Project Information",
        "progress_overview": "Overall Progress",
        "zone_progress": "Progress by Zone",
        "milestones": "Key Milestones",
        "timeline": "Progress Timeline",
        "notes": "Notes",
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
