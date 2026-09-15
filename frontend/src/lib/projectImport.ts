// What a project import can bring in, and how its result is worded — shared by
// the one Import dialog (register E1) wherever it is opened from.
import { panelParts } from "@/lib/dashboardImport";
import type { DashboardPanelsSummary } from "@/types/project";

export type ProjectImportKind = "schedule" | "dashboard";

export const IMPORT_KIND_LABELS: Record<ProjectImportKind, { title: string; hint: string }> = {
  schedule: {
    title: "P6 schedule",
    hint: "The Primavera export (or a zone tracker). Kept alongside every earlier import; the newest one is what reports read.",
  },
  dashboard: {
    title: "Dashboard workbook",
    hint: "Cash flow, progress curve, invoices and the Dashboard sheet's panels. Replaces this project's cash flow, curve and panels, and updates its invoices.",
  },
};

/** What the schedule importer reports back. */
export interface ScheduleImportResult {
  zones: number;
  subzones: number;
  activities: number;
  overall_progress: number;
  snapshot_date: string;
  source_kind?: string;
}

/** What the dashboard importer reports back — only the fields the summary reads. */
export interface DashboardImportResult {
  imported: {
    cashflow?: { months: number; first_month: string; last_month: string; curve_months?: number };
    invoices?: { periods: number; created: number; updated: number; skipped: number };
    panels?: DashboardPanelsSummary;
  };
  skipped: Record<string, string>;
}

export function scheduleSummary(r: ScheduleImportResult): string {
  return r.source_kind === "p6"
    ? `Imported the P6 schedule: ${r.activities} activities (${r.overall_progress}% overall) as of ${r.snapshot_date}.`
    : `Imported ${r.zones} zones, ${r.subzones} subzones and ${r.activities} task cells (${r.overall_progress}% overall) as of ${r.snapshot_date}.`;
}

export function dashboardSummary(r: DashboardImportResult, partNames: Record<string, string>): string {
  const parts: string[] = [];
  const cf = r.imported.cashflow;
  if (cf) {
    parts.push(`${cf.months} months of cash flow`);
    if (cf.curve_months) parts.push(`${cf.curve_months} progress-curve points`);
  }
  const inv = r.imported.invoices;
  if (inv) parts.push(`${inv.periods} invoice${inv.periods === 1 ? "" : "s"}`);
  parts.push(...panelParts(r.imported.panels));
  const missing = Object.keys(r.skipped ?? {}).map((key) => partNames[key] ?? key);
  const line = parts.length ? `Imported ${parts.join(", ")}.` : "Nothing to import.";
  // A workbook holding only some of the sheets still imports the rest, so say
  // which parts were not in it rather than reporting a clean success.
  return line + (missing.length ? ` Not in this workbook: ${missing.join(", ")}.` : "");
}
