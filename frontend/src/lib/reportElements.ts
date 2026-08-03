// Catalog behind the Report Configuration sidebar: what you can drop on a page,
// grouped the way the palette shows it. Each entry knows its default size and
// props so adding one is a single click.
import { newElementId } from "./reportLayout";
import type { ElementType, LayoutElement } from "./reportLayout";

export interface ElementSpec {
  /** Stable key — also the palette button's identity. */
  key: string;
  label: string;
  type: ElementType;
  icon: string;
  /** Default footprint in mm. */
  w: number;
  h: number;
  props?: Record<string, unknown>;
  hint?: string;
}

export interface ElementCategory {
  key: string;
  title: string;
  items: ElementSpec[];
}

/** Chart styles offered on any `chart` element (the inspector's type picker). */
export const CHART_TYPES = [
  { value: "bar", label: "Bar" },
  { value: "column", label: "Column" },
  { value: "line", label: "Line" },
  { value: "area", label: "Area" },
  { value: "pie", label: "Pie" },
  { value: "donut", label: "Donut" },
  { value: "stacked", label: "Stacked bar" },
];

/** Live values a `field` element can bind to — resolved per report at render. */
export const FIELD_SOURCES = [
  { value: "project.name", label: "Project name" },
  { value: "project.code", label: "Project code" },
  { value: "project.client", label: "Client" },
  { value: "project.consultant", label: "Consultant" },
  { value: "project.contractor", label: "Contractor" },
  { value: "project.location", label: "Location" },
  { value: "report.title", label: "Report title" },
  { value: "report.number", label: "Report number" },
  { value: "report.period", label: "Reporting period" },
  { value: "report.date", label: "Report date" },
  { value: "progress.overall", label: "Overall progress %" },
  { value: "progress.planned", label: "Planned progress %" },
  { value: "page.number", label: "Page number" },
];

/** Data behind a table element. */
export const TABLE_SOURCES = [
  { value: "project_info", label: "Project info" },
  { value: "zone_progress", label: "Progress by zone" },
  { value: "hierarchy_progress", label: "Zone / area breakdown" },
  { value: "discipline_progress", label: "Progress by trade" },
  { value: "detailed_progress", label: "Detailed activities" },
  { value: "progress_compare", label: "Plan vs actual" },
  { value: "milestones", label: "Milestones" },
  { value: "invoices", label: "Invoices" },
  { value: "submittals", label: "Submittals" },
  { value: "delays", label: "Areas of concern" },
];

/** Data behind a chart element. */
export const CHART_SOURCES = [
  { value: "zone_progress", label: "Progress by zone" },
  { value: "area_progress", label: "Progress by area" },
  { value: "scurve", label: "S-curve (planned vs actual)" },
  { value: "breakdown", label: "Completion breakdown" },
  { value: "duration", label: "Duration & delay" },
  { value: "cashflow_monthly", label: "Cash flow — monthly" },
  { value: "cashflow_cumulative", label: "Cash flow — cumulative" },
  { value: "gantt", label: "Gantt schedule" },
];

export const ELEMENT_CATALOG: ElementCategory[] = [
  {
    key: "general",
    title: "General",
    items: [
      { key: "text", label: "Text box", type: "text", icon: "text", w: 80, h: 12,
        props: { text: "Text", size: 11, color: "#1e2430", align: "left", bold: false, italic: false } },
      { key: "heading", label: "Heading", type: "text", icon: "heading", w: 100, h: 14,
        props: { text: "Section heading", size: 16, color: "#1F4E79", align: "left", bold: true } },
      { key: "image", label: "Image", type: "image", icon: "image", w: 60, h: 45,
        props: { fit: "cover" }, hint: "Placeholder until a photo is picked per report." },
      { key: "rect", label: "Rectangle", type: "rect", icon: "table", w: 60, h: 30,
        props: { fill: "#eef3f8", stroke: "#1F4E79", stroke_width: 0.5, radius: 0 } },
      { key: "ellipse", label: "Ellipse", type: "ellipse", icon: "clock", w: 40, h: 40,
        props: { fill: "#eef3f8", stroke: "#1F4E79", stroke_width: 0.5 } },
      { key: "line", label: "Line", type: "line", icon: "divider", w: 80, h: 1,
        props: { stroke: "#1F4E79", stroke_width: 0.6 } },
    ],
  },
  {
    key: "branding",
    title: "Branding & fields",
    items: [
      { key: "logo", label: "Left logo", type: "logo", icon: "companies", w: 35, h: 20,
        props: { source: "left" },
        hint: "Uploaded per-project (Report Builder → Logos)." },
      { key: "project_logo", label: "Right logo", type: "logo", icon: "projects", w: 35, h: 20,
        props: { source: "right" },
        hint: "Uploaded per-project (Report Builder → Logos)." },
      { key: "cover_image", label: "Cover image", type: "logo", icon: "image", w: 60, h: 40,
        props: { source: "cover" },
        hint: "Uploaded per-report — the project render/site photo on the cover." },
      { key: "field", label: "Live field", type: "field", icon: "hash", w: 70, h: 10,
        props: { source: "project.name", size: 11, color: "#1e2430", align: "left", bold: false,
                 label: "", show_label: false } },
      { key: "page_number", label: "Page number", type: "field", icon: "listOrdered", w: 30, h: 8,
        props: { source: "page.number", size: 10, color: "#595959", align: "right" } },
    ],
  },
  {
    key: "tables",
    title: "Progress tables",
    items: [
      { key: "table_zone", label: "Progress by zone", type: "table", icon: "table", w: 170, h: 60,
        props: { source: "zone_progress", zebra: true, border: true, header_bg: "#1F4E79", header_text: "#ffffff" } },
      { key: "table_hierarchy", label: "Zone / area breakdown", type: "table", icon: "list", w: 170, h: 70,
        props: { source: "hierarchy_progress", zebra: true, border: true, header_bg: "#1F4E79", header_text: "#ffffff" } },
      { key: "table_discipline", label: "Progress by trade", type: "table", icon: "table", w: 170, h: 55,
        props: { source: "discipline_progress", zebra: true, border: true, header_bg: "#1F4E79", header_text: "#ffffff" } },
      { key: "table_info", label: "Project info", type: "table", icon: "list", w: 170, h: 75,
        props: { source: "project_info", zebra: false, border: true, header_bg: "#1F4E79", header_text: "#ffffff" } },
      { key: "table_milestones", label: "Milestones", type: "table", icon: "flag", w: 170, h: 50,
        props: { source: "milestones", zebra: true, border: true, header_bg: "#1F4E79", header_text: "#ffffff" } },
    ],
  },
  {
    key: "charts",
    title: "Charts",
    items: [
      { key: "chart_zone", label: "Progress chart", type: "chart", icon: "dashboard", w: 120, h: 70,
        props: { source: "zone_progress", chart_type: "column", legend: true,
                 color_a: "#2E74B5", color_b: "#C0504D" } },
      { key: "chart_scurve", label: "S-curve", type: "chart", icon: "reports", w: 130, h: 75,
        props: { source: "scurve", chart_type: "line", legend: true,
                 color_a: "#2E74B5", color_b: "#C0504D" } },
      { key: "chart_breakdown", label: "Completion donut", type: "chart", icon: "clock", w: 70, h: 70,
        props: { source: "breakdown", chart_type: "donut", legend: true,
                 color_a: "#2E74B5", color_b: "#C0504D" } },
      { key: "chart_cashflow", label: "Cash flow", type: "chart", icon: "money", w: 130, h: 70,
        props: { source: "cashflow_monthly", chart_type: "bar", legend: true,
                 color_a: "#2E74B5", color_b: "#C0504D" } },
      { key: "chart_gantt", label: "Gantt schedule", type: "chart", icon: "calendar", w: 170, h: 80,
        props: { source: "gantt", chart_type: "bar", legend: false,
                 color_a: "#2E74B5", color_b: "#C0504D" } },
    ],
  },
];

/** Build a placed element from a catalog entry, centred on the drop point. */
export function createElement(spec: ElementSpec, x: number, y: number, z: number): LayoutElement {
  return {
    id: newElementId(),
    type: spec.type,
    x,
    y,
    w: spec.w,
    h: spec.h,
    z,
    props: { ...(spec.props ?? {}) },
  };
}

export function findSpec(key: string): ElementSpec | undefined {
  for (const category of ELEMENT_CATALOG) {
    const hit = category.items.find((i) => i.key === key);
    if (hit) return hit;
  }
  return undefined;
}
