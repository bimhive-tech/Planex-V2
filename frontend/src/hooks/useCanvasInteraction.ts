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
   * dragged element(s) are excluded automatically). */
  elements: LayoutElement[];
  /** Master elements (header/footer ghosts) also act as snap targets. */
  masterElements?: LayoutElement[];
  /** Commits one or more moved/resized elements at once — a multi-select
   * drag moves/resizes its whole group in a single gesture, so it must land
   * as a single undo step, not one per element. */
  onCommit: (elements: LayoutElement[]) => void;
}

/** Axis-aligned bounding box of a set of elements — the anchor a group
 * resize scales around. Ignores individual rotations (see `resizeGroupBox`'s
 * docstring) — ok for a first pass at group resize. */
function groupBoundingBox(els: LayoutElement[]): { x: number; y: number; w: number; h: number } {
  const x0 = Math.min(...els.map((e) => e.x));
  const y0 = Math.min(...els.map((e) => e.y));
  const x1 = Math.max(...els.map((e) => e.x + e.w));
  const y1 = Math.max(...els.map((e) => e.y + e.h));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

interface Gesture {
  mode: "move" | "resize" | "rotate";
  handle?: ResizeHandle;
  startX: number;
  startY: number;
  /** One element for a single-element gesture, several for a group drag —
   * their state at gesture start, so every pointermove recomputes from the
   * same baseline rather than compounding per-event drift. */
  origin: LayoutElement[];
  /** Rotate only: the element's screen-space center, fixed for the gesture. */
  centerScreen?: { x: number; y: number };
  /** Resize only, group gestures: the selection's bounding box at gesture
   * start — each member scales in proportion to where it sits inside this. */
  groupBox?: { x: number; y: number; w: number; h: number };
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
  const [draft, setDraft] = useState<LayoutElement[] | null>(null);
  const [guides, setGuides] = useState<AlignGuides | null>(null);
  // Mirrored in a ref so pointer-up can read the final value directly. Calling
  // the parent's onCommit from inside a setState updater would make that
  // updater impure — React 18 StrictMode double-invokes those, which is
  // exactly what doubled every streamed character in the AI chat.
  const draftRef = useRef<LayoutElement[] | null>(null);
  const gesture = useRef<Gesture | null>(null);
  // Kept in a ref so the window listeners (bound once per gesture) always see
  // current values without needing to rebind.
  const latest = useRef({ scale, design, elements, masterElements, onCommit });
  latest.current = { scale, design, elements, masterElements, onCommit };

  const begin = useCallback((event: React.PointerEvent, els: LayoutElement[],
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
      origin: els.map((e) => ({ ...e })),
      groupBox: mode === "resize" && els.length > 1 ? groupBoundingBox(els) : undefined,
    };
    draftRef.current = els.map((e) => ({ ...e }));
    setDraft(draftRef.current);
  }, []);

  useEffect(() => {
    function snap(value: number, fine: boolean) {
      return fine ? roundMm(value) : Math.round(value / SNAP_MM) * SNAP_MM;
    }

    function apply(next: LayoutElement[]) {
      draftRef.current = next;
      setDraft(next);
    }

    /** Single-element resize, rotation-aware — exactly the original
     * per-element math, unchanged. Only path used when exactly one element
     * is being resized. */
    function resizeOne(o: LayoutElement, handle: ResizeHandle, dx: number, dy: number, fine: boolean): LayoutElement {
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
      if (handle.includes("e")) w = Math.max(MIN_MM, snap(o.w + ldx, fine));
      else if (handle.includes("w")) w = Math.max(MIN_MM, snap(o.w - ldx, fine));
      if (handle.includes("s")) hgt = Math.max(MIN_MM, snap(o.h + ldy, fine));
      else if (handle.includes("n")) hgt = Math.max(MIN_MM, snap(o.h - ldy, fine));

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
      const fx = handle.includes("e") ? 0 : handle.includes("w") ? 1 : 0.5;
      const fy = handle.includes("s") ? 0 : handle.includes("n") ? 1 : 0.5;
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

      return {
        ...o,
        x: roundMm(Math.max(0, newCenterX - w / 2)),
        y: roundMm(Math.max(0, newCenterY - hgt / 2)),
        w: roundMm(w),
        h: roundMm(hgt),
      };
    }

    /** Group resize: scale the selection's bounding box by the drag (plain,
     * unrotated box math — the group box itself never carries a rotation of
     * its own even when members do), then re-place each member at the same
     * relative position/size it held inside the original box. Individual
     * rotations are left untouched. */
    function resizeGroup(gb: { x: number; y: number; w: number; h: number }, o: LayoutElement[],
                         handle: ResizeHandle, dx: number, dy: number, fine: boolean): LayoutElement[] {
      let w = gb.w;
      let h = gb.h;
      if (handle.includes("e")) w = Math.max(MIN_MM, snap(gb.w + dx, fine));
      else if (handle.includes("w")) w = Math.max(MIN_MM, snap(gb.w - dx, fine));
      if (handle.includes("s")) h = Math.max(MIN_MM, snap(gb.h + dy, fine));
      else if (handle.includes("n")) h = Math.max(MIN_MM, snap(gb.h - dy, fine));
      const x = handle.includes("w") ? gb.x + gb.w - w : gb.x;
      const y = handle.includes("n") ? gb.y + gb.h - h : gb.y;

      return o.map((el) => {
        const relX = gb.w > 0 ? (el.x - gb.x) / gb.w : 0;
        const relY = gb.h > 0 ? (el.y - gb.y) / gb.h : 0;
        const relW = gb.w > 0 ? el.w / gb.w : 1;
        const relH = gb.h > 0 ? el.h / gb.h : 1;
        return {
          ...el,
          x: roundMm(x + relX * w),
          y: roundMm(y + relY * h),
          w: roundMm(Math.max(MIN_MM, relW * w)),
          h: roundMm(Math.max(MIN_MM, relH * h)),
        };
      });
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
        apply([{ ...o[0], rotation: rotation % 360 }]);
        setGuides(null);
        return;
      }

      const dx = (event.clientX - g.startX) / s;
      const dy = (event.clientY - g.startY) / s;

      if (g.mode === "move") {
        if (o.length === 1) {
          const primary = o[0];
          const others = [...els, ...masters].filter((e) => e.id !== primary.id);
          const rawX = snap(primary.x + dx, fine);
          const rawY = snap(primary.y + dy, fine);
          const { x, y, guides: g2 } = computeAlignSnap(rawX, rawY, primary.w, primary.h, others, d, !fine);
          setGuides(g2.x.length || g2.y.length ? g2 : null);
          apply([clampToPage({ ...primary, x: roundMm(x), y: roundMm(y) }, d)]);
          return;
        }
        // Group move: no alignment snapping (which target would it snap to
        // with several boxes moving at once?) — just a plain grid-snapped
        // translation, applied identically to every member so their
        // relative layout never drifts.
        setGuides(null);
        const primary = o[0];
        const snappedX = snap(primary.x + dx, fine);
        const snappedY = snap(primary.y + dy, fine);
        const appliedDx = snappedX - primary.x;
        const appliedDy = snappedY - primary.y;
        apply(o.map((el) => clampToPage(
          { ...el, x: roundMm(el.x + appliedDx), y: roundMm(el.y + appliedDy) }, d,
        )));
        return;
      }

      setGuides(null);
      const h = g.handle ?? "se";
      if (o.length === 1) {
        apply([clampToPage(resizeOne(o[0], h, dx, dy, fine), d)]);
        return;
      }
      apply(resizeGroup(g.groupBox!, o, h, dx, dy, fine).map((el) => clampToPage(el, d)));
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

  const startMove = useCallback((e: React.PointerEvent, els: LayoutElement[]) => begin(e, els, "move"), [begin]);
  const startResize = useCallback(
    (e: React.PointerEvent, els: LayoutElement[], handle: ResizeHandle) => begin(e, els, "resize", handle),
    [begin],
  );
  const startRotate = useCallback((e: React.PointerEvent, el: LayoutElement) => begin(e, [el], "rotate"), [begin]);

  return { draft, guides, startMove, startResize, startRotate };
}

export const RESIZE_HANDLES: ResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
