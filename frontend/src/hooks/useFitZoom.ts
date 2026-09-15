"use client";

// Canvas zoom that starts out fitting the page to its scroll viewport's width.
import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";

/** Fit zoom snaps down to this step so the label reads 85%, not 87%. */
const FIT_STEP = 0.05;
const MIN_FIT_ZOOM = 0.25;

/**
 * Zoom state for a paper canvas. Until the user zooms by hand, the zoom
 * tracks the viewport: 100% when the page fits, otherwise the largest step
 * that fits its width — so on a laptop-width screen a landscape page no
 * longer overflows into a sideways scroll. Never auto-zooms above 100%.
 *
 * @param scrollRef the scrolling element the page sits in (its padding is excluded)
 * @param pageWidthPx the page's width in px at 100% zoom
 * @returns [zoom, setZoom] — setZoom is the manual path and ends auto-fit.
 */
export function useFitZoom(
  scrollRef: RefObject<HTMLElement | null>,
  pageWidthPx: number,
): [number, Dispatch<SetStateAction<number>>] {
  const [zoom, setZoomState] = useState(1);
  const userZoomed = useRef(false);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    function fit() {
      if (userZoomed.current || !node) return;
      const style = getComputedStyle(node);
      const available = node.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const raw = Math.floor((available / pageWidthPx) / FIT_STEP) * FIT_STEP;
      setZoomState(Math.max(MIN_FIT_ZOOM, Math.min(1, Math.round(raw * 100) / 100)));
    }
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    return () => observer.disconnect();
  }, [scrollRef, pageWidthPx]);

  const setZoom = useCallback<Dispatch<SetStateAction<number>>>((value) => {
    userZoomed.current = true;
    setZoomState(value);
  }, []);

  return [zoom, setZoom];
}
