// Synthesizes real, viewable continuation pages for a table that overflows
// its own box — see useTableOverflow (the live row data this reads) and
// apps/reports/pdf_canvas.py's _expand_table_overflow (the real PDF
// mechanism this mirrors). A synthetic page has no backing entry in the
// report's own saved `pages` array — it's derived fresh from live project
// data every time, the same way a repeating page's expansion
// (expandRepeatingPages) is, and must never be saved as real authored
// content: baking it in would freeze it exactly like the "report was
// stale for a whole session" bug from earlier this project (see
// REPORT_BUILDER_FEEDBACK.md, 2026-08-26).
import type { LayoutPage, TableDataMap, TableOverflowMap } from "./reportLayout";

/** One extra page per continuation chunk, spliced in right after the page
 * whose table produced it — same box position as the original (the real
 * PDF draws a continuation chunk at the exact same x/y/w/h, see
 * pdf_canvas._draw_table_element's `continues_chunk` branch), no caption
 * or title (the real PDF never draws either on a continuation page — same
 * function, same branch, returns before reaching that code at all). */
export function buildOverflowPages(pages: LayoutPage[], continuations: TableOverflowMap): LayoutPage[] {
  const out: LayoutPage[] = [];
  for (const page of pages) {
    out.push(page);
    for (const el of page.elements) {
      if (el.type !== "table") continue;
      const chunks = continuations[el.id];
      if (!chunks?.length) continue;
      chunks.forEach((_, idx) => {
        out.push({
          id: `${page.id}::cont::${el.id}::${idx}`,
          name: `${page.name} — continued`,
          synthetic: true,
          elements: [{
            ...el,
            id: overflowElementId(el.id, idx),
            props: { ...el.props, show_caption: false, show_title: false },
          }],
        });
      });
    }
  }
  return out;
}

/** The synthetic element id a continuation chunk's table element carries —
 * shared with overflowTableData below so TablePreview's normal
 * `tableData[el.id]` lookup finds this chunk's real rows without any
 * rendering code of its own. */
function overflowElementId(originalId: string, chunkIndex: number): string {
  return `${originalId}::cont::${chunkIndex}`;
}

/** Re-keys the same continuation data by the synthetic element ids
 * buildOverflowPages hands out, in the exact `TableDataResult` shape
 * useTableData's map already uses — merge this into that map and every
 * continuation page's table renders through the same, unmodified
 * TablePreview code path as any real table. */
export function overflowTableData(continuations: TableOverflowMap): TableDataMap {
  const out: TableDataMap = {};
  for (const [originalId, chunks] of Object.entries(continuations)) {
    chunks.forEach((chunk, idx) => { out[overflowElementId(originalId, idx)] = chunk; });
  }
  return out;
}
