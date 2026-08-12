// Report + template shapes shared across the Reports module.
import type { LayoutPage, PageDesign } from "@/lib/reportLayout";

// The template config is deeply nested and fully editable; treat it as an
// open record and read/write via dot-paths (see lib/reportTemplate).
export type ReportConfig = Record<string, unknown>;

/** A report's own page/content override — same shape as a template's canvas
 * config, minus colors/fonts/labels (those stay template-controlled). null
 * until the report's own editor is saved for the first time, at which point
 * the report renders from this instead of the template's layout. */
export interface ReportLayoutOverride {
  page_design?: PageDesign;
  layout?: { pages: LayoutPage[] };
}

export interface ReportTemplate {
  id: string;
  name: string;
  config: ReportConfig;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export type ReportStatus = "draft" | "submitted" | "approved";

export interface ReportRow {
  id: string;
  title: string;
  report_number: string;
  report_date: string | null;
  status: ReportStatus;
  project: string;
  project_name: string;
  template: string | null;
  template_name: string | null;
  period_start: string | null;
  period_finish: string | null;
  description: string;
  description_html: string;
  scope_ids: string[];
  layout_override: ReportLayoutOverride | null;
  created_at: string;
}

// Computed report data pulled from the chosen project — the builder's
// read-only Project Info + Progress Report tabs, and (see ElementPreview)
// what the Customize tab's canvas shows inside table/chart/field elements
// instead of generic placeholder content. Mirrors build_report_context()'s
// full return dict (minus binary-ish keys the asset pickers already cover).
export interface ReportZoneRow {
  id?: string; name: string; progress: number; previous?: number | null; planned?: number | null;
}
export interface ReportHierarchyRow {
  name: string; actual: number | null; previous: number | null; planned: number | null;
  children: { name: string; actual: number | null; previous: number | null; planned: number | null }[];
}
export interface ReportDisciplineRow {
  name: string; concrete: number | null; architecture: number | null;
  electrical: number | null; mechanical: number | null; other: number | null;
}
export interface ReportCriticalPathRow {
  name: string; planned_finish: string | null; forecast_finish: string | null; delay_days: number;
}
export interface ReportAreaDashboard {
  name: string; actual: number | null; planned: number | null;
  children: { name: string; actual: number | null; planned: number | null }[];
  duration: { total: number; elapsed: number; remaining: number; delay: number } | null;
}
export interface ReportData {
  report: {
    title: string; number: string; date: string | null;
    period_start: string | null; period_finish: string | null; status: string;
  };
  overall: number;
  planned: number | null;
  previous_overall: number | null;
  duration: { total: number; elapsed: number; remaining: number; delay: number } | null;
  breakdown: { total: number; completed: number; in_progress: number; not_started: number };
  zones: ReportZoneRow[];
  areas: { name: string; planned: number | null; actual: number | null }[];
  hierarchy: ReportHierarchyRow[];
  discipline: ReportDisciplineRow[];
  critical_path: ReportCriticalPathRow[];
  // Sample only (first 20) for the builder's live preview — the real PDF
  // render reads the full, unbounded list lazily (see pdf_canvas.py).
  activity_schedule: {
    name: string; baseline_duration: number | null; original_duration: number | null;
    actual_duration: number | null; remaining_duration: number | null;
    schedule_performance_index: string | null; schedule_variance: string | null;
  }[];
  // photos/attachments/logos carry a caption and an authed streaming `url`
  // (never the raw storage path — see the `data` action) — enough to count
  // and label a repeating page's real instances and show the actual image
  // on the Customize tab's canvas.
  photos: { caption: string; url: string }[];
  attachments: { caption: string; url: string }[];
  logos: {
    left: { caption: string; url: string } | null;
    right: { caption: string; url: string } | null;
    cover: { caption: string; url: string } | null;
    extra: { caption: string; url: string }[];
  };
  // area_dashboards keeps everything an item-scoped element on an expanded
  // "one per zone" page needs (item.duration/item.units/item.children),
  // minus its own nested per-zone photos.
  area_dashboards: ReportAreaDashboard[];
  cashflow: { month: string; planned: number; actual: number; cum_planned: number; cum_actual: number }[];
  cashflow_totals: { planned: number; actual: number };
  invoices: { name: string; value: number; date: string | null }[];
  invoices_total: number;
  submittals: {
    rows: { title: string; type: string; discipline: string; status: string; status_key: string;
             reference: string; date: string | null }[];
    summary: { status: string; key: string; count: number }[];
  };
  delays: { title: string; description: string; impact_days: number; status: string; date: string | null }[];
  scurve: { date: string | null; actual: number; planned: number | null }[];
  milestones: { title: string; date: string | null; status: string }[];
  snapshots: { date: string | null; overall_progress: number; source: string }[];
  project: {
    name: string; code?: string; type: string; location: string; description?: string;
    client: string; consultant: string; contractor: string;
    planned_start: string | null; planned_finish: string | null;
    revised_finish?: string | null; forecast_finish?: string | null;
    size_sqm: string | null; budget: string | null;
    contract_value?: string | null; approved_value?: string | null; forecast_cost?: string | null;
    currency: string;
  };
}

// Per-report content image (cover / progress photo / attachment / canvas
// image uploaded directly into one image element on the Customize tab).
export type ReportImageKind = "cover" | "progress" | "attachment" | "canvas";

export interface ReportImage {
  id: string;
  kind: ReportImageKind;
  kind_display: string;
  caption: string;
  sort_order: number;
  url: string;
  created_at: string;
}

// A progress photo (from the schedule tab) offered for inclusion in the report.
export interface ReportProgressPhoto {
  id: string;
  url: string;
  caption: string;
  date: string | null;
  activity_name: string;
  selected: boolean;
}
