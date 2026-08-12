"use client";

// The Customize tab's real page backgrounds — every page of the report's
// current PDF, rasterized server-side (see the `page-images` action) so the
// canvas shows the exact same pixels the real PDF has, without fighting
// pdf.js's browser-side rendering (see lib/pdfWorker.ts for that saga).
// Fetched once per reportId/refreshKey — not on every edit, since
// regenerating the PDF takes 10-20s; re-fetch only after a save.
//
// Served by the route handler (app/reports/[id]/page-images-file), not the
// /api rewrite proxy: rendering + rasterizing every page can take well over
// a minute on a large report, past the proxy's ~60s reset window (same fix
// as the PDF download and live-data routes).
import { useEffect, useState } from "react";

interface PageImagesResponse {
  pages: string[]; // base64 PNG, one per page, 1-indexed by position
  dpi: number;
}

export function useReportPageImages(reportId: string | null, refreshKey: number | string) {
  const [images, setImages] = useState<string[] | null>(null);
  // True from the very first render when a fetch is about to happen — avoids
  // a one-tick window where a caller reads loading=false before the effect
  // below has had a chance to flip it (the Customize tab used to let you
  // start dragging elements in exactly that window, before the real page
  // background had loaded).
  const [loading, setLoading] = useState(Boolean(reportId));

  useEffect(() => {
    if (!reportId) {
      setImages(null);
      return;
    }
    let alive = true;
    setLoading(true);
    fetch(`/reports/${reportId}/page-images-file`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("page-images fetch failed"))))
      .then((r: PageImagesResponse) => { if (alive) setImages(r.pages.map((b64) => `data:image/png;base64,${b64}`)); })
      .catch(() => { if (alive) setImages(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [reportId, refreshKey]);

  return { images, loading };
}
