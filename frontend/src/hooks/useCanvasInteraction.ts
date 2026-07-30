"use client";

// Pointer-driven move/resize for the report canvas.
//
// The element being dragged is held as a local `draft` and only committed on
// pointer-up: re-rendering the whole builder on every mousemove would be both
// janky and would spam the unsaved-changes flag. The canvas renders the draft
// in place of the real element while a gesture is live.
import { useCallback, useEffect, useRef, useState } from "react";

import { clampToPage, roundMm } from "@/lib/reportLayout";
import type { LayoutElement, PageDesign } from "@/lib/reportLayout";

export type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

/** Smallest element footprint, mm — below this handles overlap and it's unusable. */
const MIN_MM = 5;
/** Default snap step; hold Alt for fine placement. */
const SNAP_MM = 1;

interface Options {
  /** Pixels per millimetre the canvas is rendered at. */
  scale: number;
  design: PageDesign;
  onCommit: (element: LayoutElement) => void;
}

interface Gesture {
  mode: "move" | "resize";
  handle?: ResizeHandle;
  startX: number;
  startY: number;
  origin: LayoutElement;
}

export function useCanvasInteraction({ scale, design, onCommit }: Options) {
  const [draft, setDraft] = useState<LayoutElement | null>(null);
  // Mirrored in a ref so pointer-up can read the final value directly. Calling
  // the parent's onCommit from inside a setState updater would make that
  // updater impure — React 18 StrictMode double-invokes those, which is
  // exactly what doubled every streamed character in the AI chat.
  const draftRef = useRef<LayoutElement | null>(null);
  const gesture = useRef<Gesture | null>(null);
  // Kept in a ref so the window listeners (bound once per gesture) always see
  // current values without needing to rebind.
  const latest = useRef({ scale, design, onCommit });
  latest.current = { scale, design, onCommit };

  const begin = useCallback((event: React.PointerEvent, element: LayoutElement,
                             mode: "move" | "resize", handle?: ResizeHandle) => {
    event.preventDefault();
    event.stopPropagation();
    gesture.current = {
      mode, handle,
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
      const { scale: s, design: d } = latest.current;
      const fine = event.altKey;
      const dx = (event.clientX - g.startX) / s;
      const dy = (event.clientY - g.startY) / s;
      const o = g.origin;

      if (g.mode === "move") {
        apply(clampToPage({ ...o, x: snap(o.x + dx, fine), y: snap(o.y + dy, fine) }, d));
        return;
      }

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

  return { draft, startMove, startResize };
}

export const RESIZE_HANDLES: ResizeHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
