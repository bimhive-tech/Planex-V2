// Free-form page layout for the Template Builder's Page Designer / Report
// Configuration tabs. Everything is stored in millimetres (pages are physical
// paper, not screens) and converted to pixels only at render time via a scale.
//
// Lives under config.page_design (master, repeated on every page) and
// config.layout.pages (per-page content). The backend deep-merges stored
// config over DEFAULT_CONFIG, and replaces lists wholesale, so adding these
// keys is safe for existing templates.
import type { ReportConfig } from "@/types/report";

export type ElementType =
  | "text"
  | "image"
  | "rect"
  | "ellipse"
  | "line"
  | "logo"
  | "field"
  | "table"
  | "chart"
  | "toc";

export interface LayoutElement {
  id: string;
  type: ElementType;
  /** mm from the page's left/top edge. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** Higher renders on top. */
  z: number;
  /** Type-specific settings — see ELEMENT_CATALOG for what each type uses. */
  props: Record<string, unknown>;
}

/** Data sources a repeating page can clone itself against — mirrors
 * apps/reports/pdf_canvas.py's _REPEAT_SOURCES. */
export type RepeatSource = "photos" | "attachments" | "area_dashboards" | "zones" | "areas";

export const REPEAT_SOURCES: { value: RepeatSource; label: string }[] = [
  { value: "photos", label: "Site photos" },
  { value: "attachments", label: "Attachments" },
  { value: "area_dashboards", label: "Area dashboards (per zone)" },
  { value: "zones", label: "Zones" },
  { value: "areas", label: "Areas" },
];

export interface PageRepeat {
  source: RepeatSource;
  mode: "one_per_item" | "chunk";
  /** Items per page when mode is "chunk" (e.g. 4 photos per page). */
  chunk_size?: number;
  /** Safety cap so a huge project can't emit hundreds of pages. */
  max_pages?: number;
}

export interface LayoutPage {
  id: string;
  name: string;
  elements: LayoutElement[];
  /** Absent = a single fixed page (default). Set to clone this page once per
   * item (or per chunk of items) from a live data source. */
  repeat?: PageRepeat;
  /** Skip drawing master elements (the repeating header/logo/footer row) on
   * this page — for a bespoke page like a cover that shouldn't show the
   * running header. */
  skip_master?: boolean;
}

export interface PageDesign {
  size: PageSizeKey;
  orientation: "portrait" | "landscape";
  margin_mm: number;
  header_mm: number;
  footer_mm: number;
  show_header: boolean;
  show_footer: boolean;
  show_border: boolean;
  /** How far the border sits from the page edge, in mm — independent of
   * margin_mm (the content inset). Defaults to margin_mm when unset, so
   * older templates keep rendering exactly as before. */
  border_offset_mm?: number;
  background: string;
  /** Master elements — drawn on every page, behind page content. */
  master_elements: LayoutElement[];
}

export type PageSizeKey = "A4" | "A3" | "Letter";

/** Physical paper sizes in mm, portrait. */
export const PAGE_SIZES: Record<PageSizeKey, { w: number; h: number; label: string }> = {
  A4: { w: 210, h: 297, label: "A4 (210 × 297 mm)" },
  A3: { w: 297, h: 420, label: "A3 (297 × 420 mm)" },
  Letter: { w: 216, h: 279, label: "Letter (216 × 279 mm)" },
};

export const DEFAULT_PAGE_DESIGN: PageDesign = {
  size: "A4",
  orientation: "portrait",
  margin_mm: 16,
  header_mm: 18,
  footer_mm: 14,
  show_header: true,
  show_footer: true,
  show_border: true,
  background: "#ffffff",
  master_elements: [],
};

/** Page dimensions in mm, accounting for orientation. */
export function pageDimensions(design: PageDesign): { w: number; h: number } {
  const base = PAGE_SIZES[design.size] ?? PAGE_SIZES.A4;
  return design.orientation === "landscape" ? { w: base.h, h: base.w } : { w: base.w, h: base.h };
}

/** The content box — inside margins, below the header, above the footer. */
export function contentBox(design: PageDesign) {
  const { w, h } = pageDimensions(design);
  const top = design.margin_mm + (design.show_header ? design.header_mm : 0);
  const bottom = design.margin_mm + (design.show_footer ? design.footer_mm : 0);
  return {
    x: design.margin_mm,
    y: top,
    w: Math.max(0, w - design.margin_mm * 2),
    h: Math.max(0, h - top - bottom),
  };
}

export function newElementId(): string {
  // crypto.randomUUID needs a secure context; the fallback keeps local HTTP dev working.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `el-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function readPageDesign(config: ReportConfig): PageDesign {
  const stored = (config.page_design ?? {}) as Partial<PageDesign>;
  return { ...DEFAULT_PAGE_DESIGN, ...stored, master_elements: stored.master_elements ?? [] };
}

/**
 * Id of the implicit first page a template starts with. Deliberately a fixed
 * string, not a generated one: readPages runs on every render, and a fresh
 * random id each time meant the page you were editing never matched the page
 * the updater wrote to, so edits silently vanished.
 */
export const DEFAULT_PAGE_ID = "page-1";

export function readPages(config: ReportConfig): LayoutPage[] {
  const layout = (config.layout ?? {}) as { pages?: LayoutPage[] };
  if (layout.pages?.length) return layout.pages;
  return [{ id: DEFAULT_PAGE_ID, name: "Page 1", elements: [] }];
}

/** Round to 0.1mm so dragging doesn't accumulate float noise in saved config. */
export function roundMm(value: number): number {
  return Math.round(value * 10) / 10;
}

/** Keep an element inside the paper, preserving its size. */
export function clampToPage(el: LayoutElement, design: PageDesign): LayoutElement {
  const { w, h } = pageDimensions(design);
  return {
    ...el,
    x: roundMm(Math.min(Math.max(0, el.x), Math.max(0, w - el.w))),
    y: roundMm(Math.min(Math.max(0, el.y), Math.max(0, h - el.h))),
  };
}
