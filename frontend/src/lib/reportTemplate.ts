// Schema that drives the Template Builder. Each field maps to a dot-path inside
// the template config so the builder stays declarative — add a knob here and it
// appears in the UI. Mirrors backend apps/reports/constants.py DEFAULT_CONFIG.
import type { ReportConfig } from "@/types/report";

export type FieldType = "text" | "number" | "color" | "toggle" | "select";

export interface BuilderField {
  path: string;
  label: string;
  type: FieldType;
  options?: { value: string; label: string }[];
}

export interface BuilderSection {
  title: string;
  key: string;            // identifies the page type (drives the live preview)
  enablePath?: string;    // toggles this whole page on/off
  hint?: string;
  fields: BuilderField[];
}

const PAGE_SIZES = [{ value: "A4", label: "A4" }];
const ORIENTATIONS = [
  { value: "portrait", label: "Portrait" },
  { value: "landscape", label: "Landscape" },
];

// Tabs mirror the report's page types (matches the reference monthly report).
// Each non-Design page has an `enablePath` so it can be shown/hidden.
export const BUILDER_SECTIONS: BuilderSection[] = [
  {
    title: "Cover",
    key: "cover",
    enablePath: "cover.enabled",
    hint: "The front page: title, period, prepared-by, and project name.",
    fields: [
      { path: "cover.title", label: "Cover title", type: "text" },
      { path: "cover.subtitle", label: "Cover subtitle", type: "text" },
      { path: "cover.prepared_by", label: "Prepared-by label", type: "text" },
      { path: "cover.org", label: "Organisation", type: "text" },
      { path: "cover.show_overall", label: "Show overall %", type: "toggle" },
      { path: "cover.show_logo", label: "Show logo", type: "toggle" },
      { path: "colors.cover_bg", label: "Background", type: "color" },
      { path: "colors.cover_accent", label: "Accent", type: "color" },
      { path: "fonts.cover_title_size", label: "Title size", type: "number" },
    ],
  },
  {
    title: "Table of Contents",
    key: "toc",
    enablePath: "toc.enabled",
    fields: [
      { path: "toc.title", label: "Contents title", type: "text" },
      { path: "colors.toc_title", label: "Title color", type: "color" },
    ],
  },
  {
    title: "Project Info",
    key: "project_info",
    enablePath: "sections.project_info",
    hint: "The info table — values come from the project; rename the row labels here.",
    fields: [
      { path: "labels.project_info", label: "Section heading", type: "text" },
      { path: "labels.info_name", label: "Row: Project name", type: "text" },
      { path: "labels.info_client", label: "Row: Owner / Client", type: "text" },
      { path: "labels.info_consultant", label: "Row: Consultant", type: "text" },
      { path: "labels.info_contractor", label: "Row: Contractor", type: "text" },
      { path: "labels.info_type", label: "Row: Type", type: "text" },
      { path: "labels.info_location", label: "Row: Location", type: "text" },
      { path: "labels.info_budget", label: "Row: Project value", type: "text" },
      { path: "labels.info_start", label: "Row: Start", type: "text" },
      { path: "labels.info_finish", label: "Row: Finish", type: "text" },
      { path: "labels.info_size", label: "Row: Built-up area", type: "text" },
    ],
  },
  {
    title: "Description",
    key: "description",
    enablePath: "sections.description",
    hint: "The narrative is typed per report (Report Builder); rename the heading here.",
    fields: [{ path: "labels.description", label: "Section heading", type: "text" }],
  },
  {
    title: "Progress Report",
    key: "progress",
    enablePath: "sections.progress_overview",
    hint: "Summary, overall %, planned/actual chart, zones, milestones, and timeline.",
    fields: [
      { path: "sections.summary", label: "Show summary", type: "toggle" },
      { path: "sections.progress_chart", label: "Show planned/actual chart", type: "toggle" },
      { path: "sections.duration", label: "Show duration + delay", type: "toggle" },
      { path: "sections.scurve", label: "Show S-curve", type: "toggle" },
      { path: "sections.progress_compare", label: "Show plan-vs-actual table", type: "toggle" },
      { path: "sections.zone_progress", label: "Show zone table", type: "toggle" },
      { path: "sections.detailed_progress", label: "Show detailed activity tables", type: "toggle" },
      { path: "labels.detailed_progress", label: "Detailed heading", type: "text" },
      { path: "labels.col_task", label: "Column: Task", type: "text" },
      { path: "sections.milestones", label: "Show milestones", type: "toggle" },
      { path: "sections.timeline", label: "Show timeline", type: "toggle" },
      { path: "labels.summary", label: "Summary heading", type: "text" },
      { path: "labels.progress_overview", label: "Progress heading", type: "text" },
      { path: "labels.progress_chart", label: "Chart heading", type: "text" },
      { path: "labels.duration_section", label: "Duration heading", type: "text" },
      { path: "labels.scurve", label: "S-curve heading", type: "text" },
      { path: "labels.progress_compare", label: "Comparison heading", type: "text" },
      { path: "labels.zone_progress", label: "Zones heading", type: "text" },
      { path: "labels.milestones", label: "Milestones heading", type: "text" },
      { path: "labels.timeline", label: "Timeline heading", type: "text" },
      { path: "labels.col_zone", label: "Column: Zone", type: "text" },
      { path: "labels.col_progress", label: "Column: Progress", type: "text" },
      { path: "labels.col_planned", label: "Column: Planned %", type: "text" },
      { path: "labels.col_previous", label: "Column: Previous %", type: "text" },
      { path: "labels.col_actual", label: "Column: Actual %", type: "text" },
      { path: "labels.duration_days", label: 'Word: "Project duration"', type: "text" },
      { path: "labels.delay_days", label: 'Word: "Delay (days)"', type: "text" },
      { path: "labels.duration_elapsed", label: 'Word: "Elapsed"', type: "text" },
      { path: "labels.duration_remaining", label: 'Word: "Remaining"', type: "text" },
      { path: "labels.completed", label: 'Word: "Completed"', type: "text" },
      { path: "labels.in_progress", label: 'Word: "In Progress"', type: "text" },
      { path: "labels.not_started", label: 'Word: "Not Started"', type: "text" },
      { path: "labels.planned", label: 'Word: "Planned"', type: "text" },
      { path: "labels.actual", label: 'Word: "Actual"', type: "text" },
      { path: "colors.chart_planned", label: "Chart: planned", type: "color" },
      { path: "colors.chart_actual", label: "Chart: actual", type: "color" },
    ],
  },
  {
    title: "Progress Images",
    key: "photos",
    enablePath: "sections.photos",
    hint: "Site photos, 4 per page. Upload the photos per report (Report Builder).",
    fields: [{ path: "labels.photos", label: "Section heading", type: "text" }],
  },
  {
    title: "Delays",
    key: "delays",
    enablePath: "sections.delays",
    hint: "Obstacles & delays — logged on the project's Delays tab.",
    fields: [
      { path: "labels.delays", label: "Section heading", type: "text" },
      { path: "labels.col_delay", label: "Column: Obstacle", type: "text" },
      { path: "labels.col_impact", label: "Column: Impact (days)", type: "text" },
    ],
  },
  {
    title: "Attachments",
    key: "attachments",
    enablePath: "sections.attachments",
    hint: "Documents, one per page. Upload them per report (Report Builder).",
    fields: [{ path: "labels.attachments", label: "Section heading", type: "text" }],
  },
  {
    title: "Design",
    key: "design",
    hint: "Global styling applied across every page.",
    fields: [
      { path: "page.size", label: "Page size", type: "select", options: PAGE_SIZES },
      { path: "page.orientation", label: "Orientation", type: "select", options: ORIENTATIONS },
      { path: "page.margin_mm", label: "Margin (mm)", type: "number" },
      { path: "colors.section_heading", label: "Section headings", type: "color" },
      { path: "colors.text", label: "Body text", type: "color" },
      { path: "colors.muted", label: "Muted text", type: "color" },
      { path: "colors.table_header_bg", label: "Table header", type: "color" },
      { path: "colors.table_header_text", label: "Table header text", type: "color" },
      { path: "colors.table_border", label: "Table border", type: "color" },
      { path: "colors.table_row_alt", label: "Zebra row", type: "color" },
      { path: "fonts.h2_size", label: "Heading size", type: "number" },
      { path: "fonts.base_size", label: "Body size", type: "number" },
      { path: "fonts.line_spacing", label: "Line spacing", type: "number" },
      { path: "header.enabled", label: "Show header", type: "toggle" },
      { path: "header.org_left", label: "Header: left text", type: "text" },
      { path: "header.org_right", label: "Header: right text", type: "text" },
      { path: "footer.enabled", label: "Show footer", type: "toggle" },
      { path: "footer.show_page_number", label: "Footer: page number", type: "toggle" },
      { path: "table.zebra", label: "Zebra rows", type: "toggle" },
      { path: "table.border", label: "Table borders", type: "toggle" },
      { path: "dividers", label: "Section divider pages", type: "toggle" },
    ],
  },
];

/** Read a dot-path value out of the (nested) config. */
export function getPath(config: ReportConfig, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object") return (acc as Record<string, unknown>)[key];
    return undefined;
  }, config);
}

/** Immutably set a dot-path value, returning a new config object. */
export function setPath(config: ReportConfig, path: string, value: unknown): ReportConfig {
  const keys = path.split(".");
  const next: ReportConfig = { ...config };
  let cursor = next as Record<string, unknown>;
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    cursor[key] = { ...(cursor[key] as Record<string, unknown>) };
    cursor = cursor[key] as Record<string, unknown>;
  }
  cursor[keys[keys.length - 1]] = value;
  return next;
}
