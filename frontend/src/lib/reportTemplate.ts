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
  hint?: string;
  fields: BuilderField[];
}

const PAGE_SIZES = [{ value: "A4", label: "A4" }];
const ORIENTATIONS = [
  { value: "portrait", label: "Portrait" },
  { value: "landscape", label: "Landscape" },
];

export const BUILDER_SECTIONS: BuilderSection[] = [
  {
    title: "Page",
    fields: [
      { path: "page.size", label: "Page size", type: "select", options: PAGE_SIZES },
      { path: "page.orientation", label: "Orientation", type: "select", options: ORIENTATIONS },
      { path: "page.margin_mm", label: "Margin (mm)", type: "number" },
    ],
  },
  {
    title: "Colors",
    hint: "Used across headings, tables, and the cover.",
    fields: [
      { path: "colors.primary", label: "Primary", type: "color" },
      { path: "colors.heading", label: "Headings", type: "color" },
      { path: "colors.text", label: "Body text", type: "color" },
      { path: "colors.muted", label: "Muted text", type: "color" },
      { path: "colors.table_header_bg", label: "Table header", type: "color" },
      { path: "colors.table_header_text", label: "Table header text", type: "color" },
      { path: "colors.table_border", label: "Table border", type: "color" },
      { path: "colors.table_row_alt", label: "Zebra row", type: "color" },
      { path: "colors.cover_bg", label: "Cover background", type: "color" },
      { path: "colors.cover_accent", label: "Cover accent", type: "color" },
    ],
  },
  {
    title: "Typography",
    hint: "Font sizes in points (Amiri — supports Arabic + Latin).",
    fields: [
      { path: "fonts.cover_title_size", label: "Cover title", type: "number" },
      { path: "fonts.h1_size", label: "Heading 1", type: "number" },
      { path: "fonts.h2_size", label: "Heading 2", type: "number" },
      { path: "fonts.h3_size", label: "Heading 3", type: "number" },
      { path: "fonts.base_size", label: "Body", type: "number" },
      { path: "fonts.line_spacing", label: "Line spacing", type: "number" },
    ],
  },
  {
    title: "Cover page",
    fields: [
      { path: "cover.enabled", label: "Show cover page", type: "toggle" },
      { path: "cover.title", label: "Cover title", type: "text" },
      { path: "cover.subtitle", label: "Cover subtitle", type: "text" },
      { path: "cover.show_overall", label: "Show overall %", type: "toggle" },
      { path: "cover.show_logo", label: "Show logo", type: "toggle" },
    ],
  },
  {
    title: "Table of contents",
    fields: [
      { path: "toc.enabled", label: "Show contents page", type: "toggle" },
      { path: "toc.title", label: "Contents title", type: "text" },
    ],
  },
  {
    title: "Header & footer",
    fields: [
      { path: "header.enabled", label: "Show header", type: "toggle" },
      { path: "header.show_project", label: "Header: project name", type: "toggle" },
      { path: "header.show_report_no", label: "Header: report number", type: "toggle" },
      { path: "footer.enabled", label: "Show footer", type: "toggle" },
      { path: "footer.show_page_number", label: "Footer: page number", type: "toggle" },
      { path: "footer.text", label: "Footer text", type: "text" },
    ],
  },
  {
    title: "Sections",
    hint: "Toggle which sections appear in the report.",
    fields: [
      { path: "sections.summary", label: "Executive summary", type: "toggle" },
      { path: "sections.project_info", label: "Project information", type: "toggle" },
      { path: "sections.progress_overview", label: "Overall progress", type: "toggle" },
      { path: "sections.zone_progress", label: "Progress by zone", type: "toggle" },
      { path: "sections.milestones", label: "Key milestones", type: "toggle" },
      { path: "sections.timeline", label: "Progress timeline", type: "toggle" },
      { path: "sections.notes", label: "Notes", type: "toggle" },
      { path: "sections.photos", label: "Site photos", type: "toggle" },
    ],
  },
  {
    title: "Tables",
    fields: [
      { path: "table.header_bold", label: "Bold header", type: "toggle" },
      { path: "table.zebra", label: "Zebra rows", type: "toggle" },
      { path: "table.border", label: "Borders", type: "toggle" },
    ],
  },
  {
    title: "Labels & headings",
    hint: "Rename any heading or column — set Arabic text for a fully Arabic report.",
    fields: [
      { path: "labels.summary", label: "Summary heading", type: "text" },
      { path: "labels.project_info", label: "Project info heading", type: "text" },
      { path: "labels.progress_overview", label: "Progress heading", type: "text" },
      { path: "labels.zone_progress", label: "Zones heading", type: "text" },
      { path: "labels.milestones", label: "Milestones heading", type: "text" },
      { path: "labels.timeline", label: "Timeline heading", type: "text" },
      { path: "labels.notes", label: "Notes heading", type: "text" },
      { path: "labels.photos", label: "Photos heading", type: "text" },
      { path: "labels.col_zone", label: "Column: Zone", type: "text" },
      { path: "labels.col_progress", label: "Column: Progress", type: "text" },
      { path: "labels.col_milestone", label: "Column: Milestone", type: "text" },
      { path: "labels.col_date", label: "Column: Date", type: "text" },
      { path: "labels.col_status", label: "Column: Status", type: "text" },
      { path: "labels.col_source", label: "Column: Source", type: "text" },
      { path: "labels.overall_complete", label: 'Word: "Complete"', type: "text" },
      { path: "labels.completed", label: 'Word: "Completed"', type: "text" },
      { path: "labels.in_progress", label: 'Word: "In Progress"', type: "text" },
      { path: "labels.not_started", label: 'Word: "Not Started"', type: "text" },
      { path: "labels.activities", label: 'Word: "activities"', type: "text" },
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
