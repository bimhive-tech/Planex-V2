"use client";

// Excel-style column-width / row-height dragging for tables on the canvas.
import { useEffect, useRef, useState } from "react";

import styles from "./designer.module.css";

/** Column widths are FRACTIONS of the table width (they must stay relative:
 * the same table is drawn at several zoom levels on the canvas and again at
 * page width in the PDF). Row heights are millimetres, the unit the rest of
 * the layout already speaks. A null/missing entry means "size me automatically". */
export type Sizes = (number | null)[] | undefined;

/** Read the sizes for the tracks actually on screen. `indexMap` maps a shown
 * index to its ORIGINAL one — the stored props are keyed by original index
 * (like hidden_cols/hidden_rows), because the rendered table has hidden rows
 * and columns already stripped out server-side. */
function pick(sizes: Sizes, indexMap: number[]): (number | null)[] {
  return indexMap.map((original) => {
    const v = sizes?.[original];
    return typeof v === "number" && v > 0 ? v : null;
  });
}

/** Put edited sizes back into the ORIGINAL index space, leaving the entries
 * for hidden tracks exactly as they were so unhiding restores their size. */
function writeBack(sizes: Sizes, indexMap: number[], edited: (number | null)[]): (number | null)[] {
  const length = Math.max(sizes?.length ?? 0, ...indexMap.map((i) => i + 1), 0);
  const out: (number | null)[] = Array.from({ length }, (_, i) => sizes?.[i] ?? null);
  indexMap.forEach((original, shown) => { out[original] = edited[shown]; });
  return out;
}

/** Normalise `widths` to a full-length fraction list summing to 1.
 * Columns without an explicit width share whatever the explicit ones leave. */
export function resolveColWidths(widths: Sizes, count: number): number[] {
  const given = Array.from({ length: count }, (_, i) => {
    const v = widths?.[i];
    return typeof v === "number" && v > 0 ? v : null;
  });
  const fixed = given.reduce<number>((sum, v) => sum + (v ?? 0), 0);
  const autoCount = given.filter((v) => v === null).length;
  // Explicit widths that already claim everything leave nothing to share, so
  // fall back to an even split rather than collapsing the auto columns to 0.
  const share = autoCount ? Math.max(0, 1 - fixed) / autoCount : 0;
  const out = given.map((v) => (v === null ? share || 1 / count : v));
  const total = out.reduce((a, b) => a + b, 0) || 1;
  return out.map((v) => v / total);
}

/** <colgroup> that pins each column to its resolved fraction. Paired with
 * `table-layout: fixed` this is what stops a many-column table from growing
 * past its element box and being clipped. */
export function ColGroup({ widths, count, leadingHandle }: {
  widths: Sizes; count: number; leadingHandle?: boolean;
}) {
  // Nothing dragged yet: stay out of the way entirely. Pinning equal columns
  // here would contradict the PDF, whose per-source defaults are nothing like
  // equal (a name column is typically half the table) — and that divergence
  // would hit every existing report, not just tables someone has resized.
  if (!widths?.some((w) => typeof w === "number" && w > 0)) return null;
  const resolved = resolveColWidths(widths, count);
  return (
    <colgroup>
      {leadingHandle && <col className={styles.tableHandleCol} />}
      {/* Widths are dynamic, so they ride in on a custom property rather than
          a literal inline style (CLAUDE.md §1). */}
      {resolved.map((w, i) => (
        <col key={i} className={styles.sizedCol} style={{ ["--colW" as string]: `${w * 100}%` }} />
      ))}
    </colgroup>
  );
}

type DragState = { index: number; startPos: number; startSizes: number[]; total: number };

/**
 * Shared drag machinery for both axes. Returns the live (uncommitted) sizes so
 * the table follows the pointer, and commits once on release — one undo entry
 * per drag, not one per pixel.
 *
 * `compensate` is the difference between the two axes. Columns must keep
 * summing to the table's width, so widening one narrows its neighbour (drag a
 * boundary, exactly like Excel). Rows have no such budget — each one grows on
 * its own and pushes the rest down.
 */
function useResizeDrag(
  commit: (sizes: number[]) => void,
  axis: "x" | "y",
  minSize: number,
  compensate: boolean,
) {
  const [drag, setDrag] = useState<DragState | null>(null);
  const [live, setLive] = useState<number[] | null>(null);
  // The move/up handlers are bound once per drag, so they'd otherwise close
  // over the sizes (and the commit callback) as they were when it began.
  const latest = useRef({ drag, live, commit });
  latest.current = { drag, live, commit };

  useEffect(() => {
    if (!drag) return;
    function onMove(e: PointerEvent) {
      const d = latest.current.drag;
      if (!d) return;
      // `live` stays null until the pointer actually moves, so a stray click
      // on a grip can't silently freeze the table's sizes into the props.
      const delta = (axis === "x" ? e.clientX : e.clientY) - d.startPos;
      const next = [...d.startSizes];
      const step = delta / d.total;
      const a = d.startSizes[d.index];
      const b = d.startSizes[d.index + 1];
      if (compensate && b !== undefined) {
        const room = a + b;
        next[d.index] = Math.min(room - minSize, Math.max(minSize, a + step));
        next[d.index + 1] = room - next[d.index];
      } else {
        next[d.index] = Math.max(minSize, a + step);
      }
      setLive(next);
    }
    function onUp() {
      const { live: l, commit: c } = latest.current;
      if (l) c(l);
      setDrag(null);
      setLive(null);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    // Releasing outside the window (or the OS stealing the pointer) otherwise
    // leaves the drag armed, so the table keeps resizing with no button held.
    window.addEventListener("pointercancel", onUp);
    window.addEventListener("blur", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      window.removeEventListener("blur", onUp);
    };
  }, [drag, axis, minSize, compensate]);

  function start(e: React.PointerEvent, index: number, sizes: number[], total: number) {
    // Without this the press also reaches CanvasElementView and drags the
    // whole table element across the page instead of resizing a column.
    e.preventDefault();
    e.stopPropagation();
    setDrag({ index, startPos: axis === "x" ? e.clientX : e.clientY, startSizes: sizes, total });
  }

  return { live, start, dragging: drag !== null };
}

/** Column-edge grips, one per boundary, rendered inside the header cells.
 * `indexMap` maps each shown column to its original index (see pick). */
export function useColumnResize(widths: Sizes, indexMap: number[], commit?: (w: (number | null)[]) => void) {
  const count = indexMap.length;
  const resolved = resolveColWidths(pick(widths, indexMap), count);
  const { live, start, dragging } = useResizeDrag(
    (sizes) => commit?.(writeBack(widths, indexMap, sizes)),
    "x",
    0.04,  // never let a column shrink past ~4% — it must stay grabbable
    true,
  );
  const current = live ?? resolved;
  // No grip on the last boundary: there is no following column to take the
  // width from, so dragging it could only push the table past its box.
  const grip = commit
    ? (index: number) => index >= count - 1 ? null : (
        <span
          className={styles.colGrip}
          role="separator"
          aria-orientation="vertical"
          aria-label={`Resize column ${index + 1}`}
          onPointerDown={(e) => {
            const table = (e.currentTarget as HTMLElement).closest("table");
            // The row-handle gutter is a fixed pixel column outside the
            // fractions, so the drag denominator has to exclude it or every
            // fraction lands short by the gutter's share.
            const gutter = table?.querySelector<HTMLElement>("thead th:first-child[class*='RowHandle']");
            const total = Math.max(1, (table?.clientWidth ?? 1) - (gutter?.offsetWidth ?? 0));
            start(e, index, current, total);
          }}
        />
      )
    : undefined;
  return { widths: current, grip, dragging };
}

/** Row-edge grips. Heights are millimetres; `scale` converts to canvas px. */
export function useRowResize(
  heights: Sizes, indexMap: number[], scale: number, commit?: (h: (number | null)[]) => void,
) {
  const base = pick(heights, indexMap).map((v) => v ?? 0);  // 0 = auto
  const { live, start, dragging } = useResizeDrag(
    (sizes) => commit?.(writeBack(
      heights, indexMap, sizes.map((v) => (v > 0 ? Math.round(v * 100) / 100 : null)))),
    "y",
    2,  // mm
    false,
  );
  const current = live ?? base;
  const grip = commit
    ? (index: number) => (
        <span
          className={styles.rowGrip}
          role="separator"
          aria-orientation="horizontal"
          aria-label={`Resize row ${index + 1}`}
          onPointerDown={(e) => {
            // An auto row has no stored height yet — seed the drag from the
            // height THIS row currently measures, read at pointerdown from
            // the row itself, so it doesn't jump on the first pixel.
            const row = (e.currentTarget as HTMLElement).closest("tr");
            const measured = (row?.getBoundingClientRect().height ?? 0) / scale;
            const seeded = current.map((v, i) => (v > 0 ? v : (i === index ? measured : 0)));
            start(e, index, seeded, scale);
          }}
        />
      )
    : undefined;
  return { heights: current, grip, dragging };
}
