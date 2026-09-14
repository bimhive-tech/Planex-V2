// Wording for what a dashboard workbook import brought in, shared by the
// importer's result line and the import history so the two describe it alike.
import type { DashboardPanelsSummary } from "@/types/project";

/** What each skippable part of the import is called when a workbook lacks it. */
export const DASHBOARD_PART_NAMES: Record<string, string> = {
  cashflow: "cash flow sheet",
  invoices: "invoice sheet",
  panels: "Dashboard sheet panels (duration, submittals, BOQ, progress comparison, project tracking)",
};

/** The summary panels the report charts, as short phrases — empty when the
 * workbook carried none. */
export function panelParts(panels: DashboardPanelsSummary | undefined): string[] {
  if (!panels) return [];
  const parts: string[] = [];
  if (panels.duration) parts.push("project duration");
  if (panels.submittals) parts.push(`${panels.submittals} submittal row${panels.submittals === 1 ? "" : "s"}`);
  if (panels.boq) parts.push(`${panels.boq} BOQ categor${panels.boq === 1 ? "y" : "ies"}`);
  if (panels.progress) parts.push("progress comparison");
  if (panels.tracking) parts.push("project tracking");
  return parts;
}
