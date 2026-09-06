// Pagination for "toc" elements, mirroring apps/reports/pdf_canvas.py's
// _toc_capacity / _expand_toc_overflow. A contents or list-of-figures element
// longer than its own box continues onto extra pages in the real PDF; without
// this the Customize canvas showed one page where the download renders three,
// and every page number the contents listed was short by the pages it wasn't
// counting.
import type { LayoutElement, LayoutPage, TocCaptionsData, TocEntry } from "./reportLayout";

/** ReportLab works in points; the designer's boxes are in millimetres. */
const MM_TO_PT = 72 / 25.4;

/** Marks a "toc" element cloned onto a continuation page, and which chunk of
 * rows it draws. Rides on the element id (never its props) so it can't be
 * saved into the report the way a real prop would be — the same trick
 * buildOverflowPages uses for an overflowing table's chunks. */
const CHUNK_MARK = "::toc::";

function chunkElementId(originalId: string, chunkIndex: number): string {
  return `${originalId}${CHUNK_MARK}${chunkIndex}`;
}

/** The PAGE_ID prefix of `buildTocOverflowPages`' synthetic page ids
 * (`${page.id}::toc::${el.id}::${chunk}`) — the real page a continuation
 * was spliced after, so the "toc" element on it can still exclude that real
 * page's own row.
 *
 * A "contents" toc element skips whatever page it's drawn on (see
 * `tocRows`'s `e.id !== ownPageId`) — on the ORIGINAL page that's the page's
 * own real id, but a continuation page's real id IS that same original page
 * (it's the same logical page, split across two boxes), while its OWN id is
 * the synthetic one nothing in `entries` ever carries. Without unwrapping it
 * here, the exclusion silently did nothing on a continuation page: its row
 * list came out one entry longer than the original page's, and slicing both
 * by the same fixed window shifted the second page's rows by one, so its
 * first row silently repeated the first page's last one (found 2026-09-06,
 * "موقف الرسومات والمواد" listed as page 44 twice — once ending page 2 of
 * Contents, again starting page 3 — while the real PDF lists it once). */
export function originalPageId(pageId: string): string {
  const at = pageId.indexOf(CHUNK_MARK);
  return at === -1 ? pageId : pageId.slice(0, at);
}

/** Which chunk of its rows this element draws — 0 for the original element on
 * its own page. */
export function tocChunkIndex(elementId: string): number {
  const at = elementId.lastIndexOf(CHUNK_MARK);
  return at === -1 ? 0 : Number(elementId.slice(at + CHUNK_MARK.length)) || 0;
}

/** How many rows fit this element's box — pdf_canvas._toc_capacity exactly,
 * converted from the designer's millimetres to the points it works in. */
export function tocCapacity(el: LayoutElement): number {
  const size = Number(el.props.size ?? 11);
  const rowH = Number(el.props.row_height ?? 8) * MM_TO_PT;
  const h = Number(el.h ?? 0) * MM_TO_PT;
  return Math.max(1, Math.floor((h - size) / rowH) + 1);
}

/** The rows a "toc" element resolves to, before pagination — mirrors
 * pdf_canvas._toc_rows (same variants, same "skip my own page" and
 * exclude-cover rules for the contents list). */
export function tocRows(
  el: LayoutElement, ownPageId: string, entries: TocEntry[], captions: TocCaptionsData | undefined,
): { name: string; page: number; id?: string }[] {
  const variant = String(el.props.variant ?? "contents");
  if (variant !== "contents") {
    const rows = captions?.[variant as "tables" | "figures" | "images"] ?? [];
    return rows.map((r) => ({ name: r.text, page: r.page }));
  }
  const excludeCover = el.props.exclude_cover ?? true;
  return entries
    .filter((e) => !e.synthetic)
    .filter((e) => e.id !== ownPageId)
    .filter((e) => !(excludeCover && e.name.trim().toLowerCase() === "cover"))
    .map((e) => ({ name: e.name, page: e.number, id: e.id }));
}

/**
 * One extra page per chunk of rows a "toc" element can't fit, spliced in
 * right after the page it overflows from — mirrors
 * pdf_canvas._expand_toc_overflow, including its one-overflowing-element-
 * per-page scope (the first one that overflows wins; the PDF splits no more
 * than one element per page either).
 *
 * `entries` and `captions` are what the rows are counted from, so this has to
 * run on a page list that already has the table-overflow pages spliced in —
 * the same order build_canvas_pdf uses (tables, then a numbering pass, then
 * this), because a continuation page shifts every number after it.
 */
export function buildTocOverflowPages(
  pages: LayoutPage[], entries: TocEntry[], captions: TocCaptionsData | undefined,
): LayoutPage[] {
  const out: LayoutPage[] = [];
  for (const page of pages) {
    out.push(page);
    if (page.synthetic) continue;
    const el = page.elements.find(
      (e) => e.type === "toc" && tocRows(e, page.id, entries, captions).length > tocCapacity(e));
    if (!el) continue;
    const total = tocRows(el, page.id, entries, captions).length;
    const capacity = tocCapacity(el);
    for (let chunk = 1; chunk * capacity < total; chunk += 1) {
      out.push({
        id: `${page.id}::toc::${el.id}::${chunk}`,
        name: `${page.name} — continued`,
        synthetic: true,
        // The real PDF draws a continuation chunk in the same box, with no
        // title or caption (pdf_canvas._draw_toc_element returns before both).
        elements: [{ ...el, id: chunkElementId(el.id, chunk), props: { ...el.props, show_title: false } }],
        // Same fix as buildOverflowPages' table continuations: a landscape
        // toc page's overflow must stay landscape too.
        orientation: page.orientation,
      });
    }
  }
  return out;
}

/** Every page's real name and real page number, for any "toc" element on the
 * canvas — mirrors build_canvas_pdf's toc_map/toc_order pre-pass: numbering
 * counts EVERY page the PDF prints. A synthetic continuation page still gets
 * an entry (marked `synthetic`) so a page-number field on it resolves to its
 * own real number — see ElementPreview's "field" case — but a Contents/
 * List-of-X listing must filter those out itself (see `tocRows`), the same
 * way the real PDF never lists a continuation page under its own name. */
export function tocEntriesFor(pages: LayoutPage[]): TocEntry[] {
  return pages.map((p, i) => ({ id: p.id, name: p.name, number: i + 1, synthetic: p.synthetic }));
}
