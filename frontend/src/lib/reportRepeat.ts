// Expands a repeating page's abstract "clone per item" rule into concrete,
// independently-editable pages — one per real item (or chunk) — so the
// report Customize tab's page count and labels match what the real PDF
// renders (e.g. 19 actual pages) instead of the template's 13 page *types*.
import { newElementId } from "./reportLayout";
import type { LayoutPage, RepeatSource } from "./reportLayout";
import type { ReportData } from "@/types/report";

function itemLabels(source: RepeatSource, data: ReportData): string[] {
  switch (source) {
    case "zones": return data.zones.map((z) => z.name);
    case "areas": return data.areas.map((a) => a.name);
    case "area_dashboards": return data.area_dashboards.map((a) => a.name);
    case "photos": return data.photos.map((p, i) => p.caption || `Photo ${i + 1}`);
    case "attachments": return data.attachments.map((a, i) => a.caption || `Attachment ${i + 1}`);
    default: return [];
  }
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** One concrete page per real item/chunk a repeating page would produce at
 * render time, cloned from its elements and pinned (repeat.pin_index) to
 * that exact position — turning one abstract repeating page into N fixed,
 * independently-editable ones. Non-repeating pages pass through unchanged.
 * A repeat source with nothing in it is dropped entirely, matching what the
 * real PDF does (an empty source skips the page). */
export function expandRepeatingPages(pages: LayoutPage[], data: ReportData): LayoutPage[] {
  const out: LayoutPage[] = [];
  for (const page of pages) {
    const rep = page.repeat;
    if (!rep) {
      out.push(page);
      continue;
    }
    const labels = itemLabels(rep.source, data);
    if (!labels.length) continue;
    const cap = rep.max_pages ?? 60;
    const groups = rep.mode === "chunk"
      ? chunk(labels, Math.max(1, rep.chunk_size ?? 4)).slice(0, cap)
      : labels.slice(0, cap).map((l) => [l]);

    groups.forEach((group, i) => {
      const label = group.length > 1 ? `${group[0]} – ${group[group.length - 1]}` : group[0];
      out.push({
        id: newElementId(),
        name: `${page.name} — ${label}`,
        elements: page.elements.map((e) => ({ ...e, id: newElementId(), props: { ...e.props } })),
        repeat: { ...rep, pin_index: i },
        skip_master: page.skip_master,
      });
    });
  }
  return out;
}
