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
      // The resize handles are drawn on the element's own box, which is
      // visually rotated (CSS transform, around its center) — a raw
      // screen-space pointer delta doesn't line up with the element's own
      // width/height axes once it's rotated (drag "right" on a 90°-rotated
      // box and you're actually dragging along its height, not its width).
      // Rotate the delta into the element's local, unrotated frame first;
      // for rotation 0 this is the identity (cos 0=1, sin 0=0), so unrotated
      // elements resize exactly as before.
      const rot = ((o.rotation ?? 0) * Math.PI) / 180;
      const cosR = Math.cos(rot);
      const sinR = Math.sin(rot);
      const ldx = dx * cosR + dy * sinR;
      const ldy = -dx * sinR + dy * cosR;

      let w = o.w;
      let hgt = o.h;
      if (h.includes("e")) w = Math.max(MIN_MM, snap(o.w + ldx, fine));
      else if (h.includes("w")) w = Math.max(MIN_MM, snap(o.w - ldx, fine));
      if (h.includes("s")) hgt = Math.max(MIN_MM, snap(o.h + ldy, fine));
      else if (h.includes("n")) hgt = Math.max(MIN_MM, snap(o.h - ldy, fine));

      // CSS rotates the box around its own center (transform-origin default),
      // and that center moves whenever w/h changes — so just keeping the
      // *local* opposite edge's x/y fixed (as the old code did) still lets a
      // rotated box visibly swing/drift on screen as it resizes. Instead,
      // solve for the x/y that keeps the opposite corner/edge's actual
      // *screen* position fixed: locate that anchor once (in the original,
      // unresized box), then re-derive the new box's position so the same
      // anchor lands back on that exact screen point after rotation. At
      // rotation 0 this reduces to exactly the old "opposite edge stays put"
      // behavior — verified algebraically, not just visually.
      const fx = h.includes("e") ? 0 : h.includes("w") ? 1 : 0.5;
      const fy = h.includes("s") ? 0 : h.includes("n") ? 1 : 0.5;
      const oldCenterX = o.x + o.w / 2;
      const oldCenterY = o.y + o.h / 2;
      const oldOffX = (fx - 0.5) * o.w;
      const oldOffY = (fy - 0.5) * o.h;
      const anchorX = oldCenterX + oldOffX * cosR - oldOffY * sinR;
      const anchorY = oldCenterY + oldOffX * sinR + oldOffY * cosR;
      const newOffX = (fx - 0.5) * w;
      const newOffY = (fy - 0.5) * hgt;
      const newCenterX = anchorX - (newOffX * cosR - newOffY * sinR);
      const newCenterY = anchorY - (newOffX * sinR + newOffY * cosR);
      const x = newCenterX - w / 2;
      const y = newCenterY - hgt / 2;

      apply(clampToPage({
        ...o,
        x: roundMm(Math.max(0, x)),
        y: roundMm(Math.max(0, y)),
        w: roundMm(w),
        h: roundMm(hgt),
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
