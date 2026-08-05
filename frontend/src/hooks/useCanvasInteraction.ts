"use client";

// Pointer-driven move/resize/rotate for the report canvas, plus Canva-style
// alignment snapping while moving.
//
// The element being dragged is held as a local `draft` and only committed on
// pointer-up: re-rendering the whole builder on every mousemove would be both
// janky and would spam the unsaved-changes flag. The canvas renders the draft
// in place of the real element while a gesture is live.
import { useCallback, useEffect, useRef, useState } from "react";

import { clampToPage, contentBox, pageDimensions, roundMm } from "@/lib/reportLayout";
import type { LayoutElement, PageDesign } from "@/lib/reportLayout";

export type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

/** Smallest element footprint, mm — below this handles overlap and it's unusable. */
const MIN_MM = 5;
/** Default snap step; hold Alt for fine placement. */
const SNAP_MM = 1;
/** How close (mm) an edge/center needs to be to another element (or the page/
 * content-box edges and centers) before it snaps into alignment. */
const ALIGN_SNAP_MM = 2;
/** Rotation snaps to 15° steps unless Alt is held. */
const ROTATE_SNAP_DEG = 15;

interface Options {
  /** Pixels per millimetre the canvas is rendered at. */
  scale: number;
  design: PageDesign;
  /** This page's own elements — snap targets for alignment guides (the
   * dragged element itself is excluded automatically). */
  elements: LayoutElement[];
  /** Master elements (header/footer ghosts) also act as snap targets. */
  masterElements?: LayoutElement[];
  onCommit: (element: LayoutElement) => void;
}

interface Gesture {
  mode: "move" | "resize" | "rotate";
  handle?: ResizeHandle;
  startX: number;
  startY: number;
  origin: LayoutElement;
  /** Rotate only: the element's screen-space center, fixed for the gesture. */
  centerScreen?: { x: number; y: number };
}

export interface AlignGuides {
  /** Vertical guide lines, as x positions in mm. */
  x: number[];
  /** Horizontal guide lines, as y positions in mm. */
  y: number[];
}

function snapAxis(candidates: number[], targets: number[]): { delta: number; guide: number | null } {
  let best = ALIGN_SNAP_MM;
  let delta = 0;
  let guide: number | null = null;
  for (const c of candidates) {
    for (const t of targets) {
      const dist = Math.abs(c - t);
      if (dist < best) {
        best = dist;
        delta = t - c;
        guide = t;
      }
    }
  }
  return { delta, guide };
}

/** Snap a candidate top-left position to align with other elements' edges/
 * centers, or the page/content-box edges/center — mirrors Canva's alignment
 * guides. Returns the (possibly adjusted) position plus any guide lines to
 * draw. Skipped entirely when `active` is false (Alt held = free placement). */
function computeAlignSnap(
  x: number, y: number, w: number, h: number,
  others: { x: number; y: number; w: number; h: number }[],
  design: PageDesign, active: boolean,
): { x: number; y: number; guides: AlignGuides } {
  if (!active) return { x, y, guides: { x: [], y: [] } };

  const { w: pageW, h: pageH } = pageDimensions(design);
  const box = contentBox(design);
  const xTargets = [0, pageW, pageW / 2, box.x, box.x + box.w, box.x + box.w / 2];
  const yTargets = [0, pageH, pageH / 2, box.y, box.y + box.h, box.y + box.h / 2];
  for (const o of others) {
    xTargets.push(o.x, o.x + o.w / 2, o.x + o.w);
    yTargets.push(o.y, o.y + o.h / 2, o.y + o.h);
  }

  const xResult = snapAxis([x, x + w / 2, x + w], xTargets);
  const yResult = snapAxis([y, y + h / 2, y + h], yTargets);

  return {
    x: x + xResult.delta,
    y: y + yResult.delta,
    guides: {
      x: xResult.guide !== null ? [xResult.guide] : [],
      y: yResult.guide !== null ? [yResult.guide] : [],
    },
  };
}

export function useCanvasInteraction({ scale, design, elements, masterElements = [], onCommit }: Options) {
  const [draft, setDraft] = useState<LayoutElement | null>(null);
  const [guides, setGuides] = useState<AlignGuides | null>(null);
  // Mirrored in a ref so pointer-up can read the final value directly. Calling
  // the parent's onCommit from inside a setState updater would make that
  // updater impure — React 18 StrictMode double-invokes those, which is
  // exactly what doubled every streamed character in the AI chat.
  const draftRef = useRef<LayoutElement | null>(null);
  const gesture = useRef<Gesture | null>(null);
  // Kept in a ref so the window listeners (bound once per gesture) always see
  // current values without needing to rebind.
  const latest = useRef({ scale, design, elements, masterElements, onCommit });
  latest.current = { scale, design, elements, masterElements, onCommit };

  const begin = useCallback((event: React.PointerEvent, element: LayoutElement,
                             mode: "move" | "resize" | "rotate", handle?: ResizeHandle) => {
    event.preventDefault();
    event.stopPropagation();
    const centerScreen = mode === "rotate"
      ? (() => {
          const r = (event.target as HTMLElement).closest("[data-canvas-element]")?.getBoundingClientRect();
          return r ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : { x: event.clientX, y: event.clientY };
        })()
      : undefined;
    gesture.current = {
      mode, handle, centerScreen,
      startX: event.clientX,
      startY: event.clientY,
      origin: { ...element },
    };
    draftRef.current = { ...element };
    setDraft(draftRef.current);
  }, []);

  useEffect(() => {
    function snap(value: number, fine: boolean) {
      return fine ? roundMm(value) : Math.round(value / SNAP_MM) * SNAP_MM;
    }

    function apply(next: LayoutElement) {
      draftRef.current = next;
      setDraft(next);
    }

    function onMove(event: PointerEvent) {
      const g = gesture.current;
      if (!g) return;
      const { scale: s, design: d, elements: els, masterElements: masters } = latest.current;
      const fine = event.altKey;
      const o = g.origin;

      if (g.mode === "rotate") {
        const c = g.centerScreen!;
        const angle = (Math.atan2(event.clientY - c.y, event.clientX - c.x) * 180) / Math.PI + 90;
        const normalized = ((angle % 360) + 360) % 360;
        const rotation = fine ? Math.round(normalized) : Math.round(normalized / ROTATE_SNAP_DEG) * ROTATE_SNAP_DEG;
        apply({ ...o, rotation: rotation % 360 });
        setGuides(null);
        return;
      }

      const dx = (event.clientX - g.startX) / s;
      const dy = (event.clientY - g.startY) / s;

      if (g.mode === "move") {
        const others = [...els, ...masters].filter((e) => e.id !== o.id);
        const rawX = snap(o.x + dx, fine);
        const rawY = snap(o.y + dy, fine);
        const { x, y, guides: g2 } = computeAlignSnap(rawX, rawY, o.w, o.h, others, d, !fine);
        setGuides(g2.x.length || g2.y.length ? g2 : null);
        apply(clampToPage({ ...o, x: roundMm(x), y: roundMm(y) }, d));
        return;
      }

      setGuides(null);
      const h = g.handle ?? "se";
      let { x, y, w, hgt } = { x: o.x, y: o.y, w: o.w, hgt: o.h };

      if (h.includes("w")) {
        // Dragging the left edge moves x and shrinks w by the same amount.
        const nx = snap(o.x + dx, fine);
        const maxX = o.x + o.w - MIN_MM;
        x = Math.min(nx, maxX);
        w = o.x + o.w - x;
      }
      if (h.includes("e")) w = Math.max(MIN_MM, snap(o.w + dx, fine));
      if (h.includes("n")) {
        const ny = snap(o.y + dy, fine);
        const maxY = o.y + o.h - MIN_MM;
        y = Math.min(ny, maxY);
        hgt = o.y + o.h - y;
      }
      if (h.includes("s")) hgt = Math.max(MIN_MM, snap(o.h + dy, fine));

      apply(clampToPage({
        ...o,
        x: roundMm(Math.max(0, x)),
        y: roundMm(Math.max(0, y)),
        w: roundMm(Math.max(MIN_MM, w)),
        h: roundMm(Math.max(MIN_MM, hgt)),
      }, d));
    }

    function onUp() {
      if (!gesture.current) return;
      gesture.current = null;
      const final = draftRef.current;
      draftRef.current = null;
      setDraft(null);
      setGuides(null);
      if (final) latest.current.onCommit(final);
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, []);

  const startMove = useCallback((e: React.PointerEvent, el: LayoutElement) => begin(e, el, "move"), [begin]);
  const startResize = useCallback(
    (e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) => begin(e, el, "resize", handle),
    [begin],
  );
  const startRotate = useCallback((e: React.PointerEvent, el: LayoutElement) => begin(e, el, "rotate"), [begin]);

  return { draft, guides, startMove, startResize, startRotate };
}

export const RESIZE_HANDLES: ResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
