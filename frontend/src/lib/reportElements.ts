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
  { value: "gauge", label: "Gauge" },
];

/** Live values a `field` element can bind to — resolved per report at render. */
export const FIELD_SOURCES = [
  { value: "project.name", label: "Project name" },
  { value: "project.code", label: "Project code" },
  { value: "project.client", label: "Client" },
  { value: "project.consultant", label: "Consultant" },
  { value: "project.contractor", label: "Contractor" },
  { value: "project.location", label: "Location" },
  { value: "project.description", label: "Project description" },
  { value: "report.title", label: "Report title" },
  { value: "report.number", label: "Report number" },
  { value: "report.period", label: "Reporting period" },
  { value: "report.date", label: "Report date" },
  { value: "progress.overall", label: "Overall progress %" },
  { value: "progress.planned", label: "Planned progress %" },
  { value: "page.number", label: "Page number" },
  { value: "page.title", label: "Page title (this page's own name)" },
];

/** Data behind a table element. */
export const TABLE_SOURCES = [
  { value: "project_info", label: "Project info" },
  { value: "zone_progress", label: "Progress by zone" },
  { value: "hierarchy_progress", label: "Zone / area breakdown" },
  { value: "discipline_progress", label: "Progress by trade" },
  { value: "detailed_progress", label: "Detailed activities" },
  { value: "critical_path_delays", label: "Critical path delays" },
  { value: "activity_schedule", label: "Activity schedule detail (durations, SPI, variance)" },
  { value: "progress_compare", label: "Plan vs actual" },
  { value: "milestones", label: "Milestones" },
  { value: "invoices", label: "Invoices" },
  { value: "submittals", label: "Submittals" },
  { value: "delays", label: "Areas of concern" },
  { value: "custom", label: "Custom table (build your own)" },
];

/** Data behind a chart element. */
export const CHART_SOURCES = [
  { value: "zone_progress", label: "Progress by zone" },
  { value: "area_progress", label: "Progress by area" },
  { value: "scurve", label: "S-curve (planned vs actual)" },
  { value: "breakdown", label: "Completion breakdown" },
  { value: "spi", label: "SPI gauge (overall)" },
  { value: "duration", label: "Duration & delay" },
  { value: "cashflow_monthly", label: "Cash flow — monthly" },
  { value: "cashflow_cumulative", label: "Cash flow — cumulative" },
  { value: "invoice_status", label: "Invoice status (invoiced vs remaining)" },
  { value: "budget_total_cost", label: "Budget total cost" },
  { value: "boq_financial_progress", label: "Financial progress by BOQ" },
  { value: "progress_comparison", label: "Progress comparison (planned/actual/earned value)" },
  { value: "progress_tracking", label: "Project tracking (previous vs current month)" },
  { value: "gantt", label: "Gantt schedule" },
  { value: "submittals_material", label: "Material submittals by status/discipline" },
  { value: "submittals_shop_drawing", label: "Shop drawings by status/discipline" },
];

// Only offered on a page marked "repeat" — resolved against the item the
// current clone is showing, not the whole project (e.g. "item.name" on a
// per-zone page reads THAT zone's name, not the first one's).
export const ITEM_FIELD_SOURCES = [
  { value: "item.name", label: "Item: name" },
  { value: "item.progress", label: "Item: progress %" },
  { value: "item.planned", label: "Item: planned %" },
  { value: "item.previous", label: "Item: previous %" },
  { value: "item.caption", label: "Item: caption" },
  { value: "item.index", label: "Item: number (1, 2, 3…)" },
  { value: "item.count", label: "Item: total count" },
];

export const ITEM_TABLE_SOURCES = [
  { value: "item.children", label: "Item: sub-areas" },
];

export const ITEM_CHART_SOURCES = [
  { value: "item.units", label: "Item: unit progress" },
  { value: "item.duration", label: "Item: duration & delay" },
  { value: "item.spi", label: "Item: SPI gauge" },
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
        props: { fit: "cover", border: false }, hint: "Placeholder until a photo is picked per report." },
      { key: "photo_slot", label: "Photo slot", type: "image", icon: "image", w: 75, h: 55,
        props: { source: "repeat.item", slot: 0, show_caption: true, fit: "contain", border: false },
        hint: "Only fills in on a repeating page (e.g. Site Photos) — pick which slot in the Properties panel." },
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
        props: { source: "left", border: false },
        hint: "Uploaded per-project (Report Builder → Logos)." },
      { key: "project_logo", label: "Right logo", type: "logo", icon: "projects", w: 35, h: 20,
        props: { source: "right", border: false },
        hint: "Uploaded per-project (Report Builder → Logos)." },
      { key: "cover_image", label: "Cover image", type: "logo", icon: "image", w: 60, h: 40,
        props: { source: "cover", border: false },
        hint: "Uploaded per-report — the project render/site photo on the cover." },
      { key: "extra_logo", label: "Additional logo", type: "logo", icon: "companies", w: 30, h: 18,
        props: { source: "extra", slot: 0, border: false },
        hint: "Beyond left/right — any number of partner logos, uploaded per-project (Report Builder → Logos). Pick which one in the Properties panel." },
      { key: "field", label: "Live field", type: "field", icon: "hash", w: 70, h: 10,
        props: { source: "project.name", size: 11, color: "#1e2430", align: "left", bold: false,
                 label: "", show_label: false } },
      { key: "page_number", label: "Page number", type: "field", icon: "listOrdered", w: 30, h: 8,
        props: { source: "page.number", size: 10, color: "#595959", align: "right" } },
      { key: "divider_heading", label: "Divider heading", type: "field", icon: "heading", w: 170, h: 20,
        props: { source: "page.title", size: 22, color: "#1F4E79", align: "center", bold: true },
        hint: "Drop on an otherwise-blank page to reproduce the classic section-divider "
          + "look — the page's own name, centered and large. Add a Line element under it "
          + "for the reference's underline rule." },
      { key: "toc", label: "Table of contents", type: "toc", icon: "list", w: 170, h: 120,
        props: { size: 11, row_height: 8, color: "#1e2430", exclude_cover: true, variant: "contents" },
        hint: "Lists every other page in this template with its real page number — resolved at render time, no manual upkeep." },
      { key: "toc_tables", label: "List of tables", type: "toc", icon: "table", w: 170, h: 100,
        props: { size: 11, row_height: 8, color: "#1e2430", variant: "tables" },
        hint: "Lists every table with its Properties panel \"Show caption\" turned on, numbered in the order they appear in the PDF." },
      { key: "toc_figures", label: "List of figures", type: "toc", icon: "dashboard", w: 170, h: 100,
        props: { size: 11, row_height: 8, color: "#1e2430", variant: "figures" },
        hint: "Lists every chart with \"Show caption\" turned on, numbered in the order they appear in the PDF." },
      { key: "toc_images", label: "List of images", type: "toc", icon: "image", w: 170, h: 100,
        props: { size: 11, row_height: 8, color: "#1e2430", variant: "images" },
        hint: "Lists every captioned Site Photos slot, numbered in the order it appears in the PDF." },
      { key: "description", label: "Description", type: "description", icon: "text", w: 170, h: 220,
        props: { html: "" },
        hint: "A rich-text block you write and format right here — double-click to start typing, insert "
          + "tables/charts/images inline. Continues onto extra pages if it doesn't fit this box." },
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
      { key: "table_critical_path", label: "Critical path delays", type: "table", icon: "flag", w: 170, h: 60,
        props: { source: "critical_path_delays", zebra: true, border: true, header_bg: "#1F4E79", header_text: "#ffffff" } },
      { key: "table_custom", label: "Custom table", type: "table", icon: "table", w: 170, h: 60,
        props: { source: "custom", zebra: true, border: true, header_bg: "#1F4E79", header_text: "#ffffff",
                 custom_data: { columns: ["Column 1", "Column 2"], rows: [["", ""], ["", ""]] } },
        hint: "Build a table from scratch, or paste cells copied from Excel straight into it." },
    ],
  },
  {
    key: "charts",
    title: "Charts",
    items: [
      { key: "chart_zone", label: "Progress chart", type: "chart", icon: "dashboard", w: 120, h: 70,
        props: { source: "zone_progress", chart_type: "column", legend: true,
                 color_a: "#4F81BD", color_b: "#C0504D" } },
      { key: "chart_scurve", label: "S-curve", type: "chart", icon: "reports", w: 130, h: 75,
        props: { source: "scurve", chart_type: "line", legend: true,
                 color_a: "#4F81BD", color_b: "#C0504D" } },
      { key: "chart_breakdown", label: "Completion donut", type: "chart", icon: "clock", w: 70, h: 70,
        props: { source: "breakdown", chart_type: "donut", legend: true,
                 color_a: "#4F81BD", color_b: "#C0504D" } },
      { key: "chart_spi", label: "SPI gauge", type: "chart", icon: "dashboard", w: 65, h: 45,
        props: { source: "spi", chart_type: "gauge", legend: false } },
      { key: "chart_cashflow", label: "Cash flow", type: "chart", icon: "money", w: 130, h: 70,
        props: { source: "cashflow_monthly", chart_type: "bar", legend: true,
                 color_a: "#4F81BD", color_b: "#C0504D" } },
      { key: "chart_gantt", label: "Gantt schedule", type: "chart", icon: "calendar", w: 170, h: 80,
        props: { source: "gantt", chart_type: "bar", legend: false,
                 color_a: "#4F81BD", color_b: "#C0504D" } },
      { key: "chart_submittals", label: "Material submittals", type: "chart", icon: "table", w: 150, h: 60,
        props: { source: "submittals_material", chart_type: "stacked", legend: true },
        hint: "Status (submitted/approved/rejected/pending) by discipline, stacked bars." },
      { key: "chart_shop_drawings", label: "Shop drawings", type: "chart", icon: "table", w: 150, h: 60,
        props: { source: "submittals_shop_drawing", chart_type: "stacked", legend: true },
        hint: "Same breakdown as Material submittals, for shop drawing records." },
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
