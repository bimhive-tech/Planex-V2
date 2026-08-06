// Expands a repeating page's abstract "clone per item" rule into concrete,
// independently-editable pages — one per real item (or chunk) — so the
// report Customize tab's page count and labels match what the real PDF
// renders (e.g. 19 actual pages) instead of the template's 13 page *types*.
import { newElementId } from "./reportLayout";
import type { LayoutPage, RepeatSource } from "./reportLayout";
import type { ReportData } from "@/types/report";

/** A repeat source's real items, as loosely-typed records — the various
 * sources use different keys for the same idea (zones: "progress",
 * areas/area_dashboards: "actual"), mirrored by resolveItemField below,
 * same as apps/reports/pdf_canvas.py's _resolve_item_field does server-side. */
export type RepeatItem = Record<string, unknown>;

function itemsFor(source: RepeatSource, data: ReportData): RepeatItem[] {
  switch (source) {
    case "zones": return data.zones as unknown as RepeatItem[];
    case "areas": return data.areas as unknown as RepeatItem[];
    case "area_dashboards": return data.area_dashboards as unknown as RepeatItem[];
    case "photos": return data.photos as unknown as RepeatItem[];
    case "attachments": return data.attachments as unknown as RepeatItem[];
    default: return [];
  }
}

function labelOf(item: RepeatItem, fallback: string): string {
  return String(item.name ?? item.caption ?? fallback);
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
    const items = itemsFor(rep.source, data);
    if (!items.length) continue;
    const cap = rep.max_pages ?? 60;
    const groups = rep.mode === "chunk"
      ? chunk(items, Math.max(1, rep.chunk_size ?? 4)).slice(0, cap)
      : items.slice(0, cap).map((it) => [it]);

    groups.forEach((group, i) => {
      const first = labelOf(group[0], `Item ${i + 1}`);
      const label = group.length > 1 ? `${first} – ${labelOf(group[group.length - 1], "")}` : first;
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

/** The specific item (or chunk group) an expanded page is pinned to, so its
 * item.* field/table/chart elements can resolve real data instead of the
 * generic placeholder. null for a page that isn't pinned (a fixed page, or
 * still the abstract un-expanded repeating page from the Template Builder). */
export function resolvePinnedItem(page: LayoutPage, data: ReportData): RepeatItem | RepeatItem[] | null {
  const rep = page.repeat;
  if (!rep || rep.pin_index == null) return null;
  const items = itemsFor(rep.source, data);
  if (rep.mode === "chunk") {
    const size = Math.max(1, rep.chunk_size ?? 4);
    const groups = chunk(items, size);
    return groups[rep.pin_index] ?? null;
  }
  return items[rep.pin_index] ?? null;
}

/** Mirrors apps/reports/pdf_canvas.py's _resolve_item_field: reads an
 * item.* FIELD_SOURCES key off one resolved item (never a chunk group —
 * item.name/progress/etc. only make sense for a single item). */
export function resolveItemField(source: string, item: RepeatItem | null): string | null {
  if (!item) return null;
  const key = source.startsWith("item.") ? source.slice(5) : source;
  if (key === "name") return item.name != null ? String(item.name) : null;
  if (key === "caption") return item.caption != null ? String(item.caption) : null;
  if (key === "progress" || key === "planned" || key === "previous") {
    const value = key === "progress" ? (item.progress ?? item.actual) : item[key];
    return typeof value === "number" ? `${value.toFixed(1)}%` : null;
  }
  return null;
}
