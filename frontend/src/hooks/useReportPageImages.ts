"use client";

// The Customize tab's real page backgrounds — every page of the report's
// current PDF, rasterized server-side (see the `page-images` action) so the
// canvas shows the exact same pixels the real PDF has, without fighting
// pdf.js's browser-side rendering (see lib/pdfWorker.ts for that saga).
// Fetched once per reportId/refreshKey — not on every edit, since
// regenerating the PDF takes 10-20s; re-fetch only after a save.
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

interface PageImagesResponse {
  pages: string[]; // base64 PNG, one per page, 1-indexed by position
  dpi: number;
}

export function useReportPageImages(reportId: string | null, refreshKey: number | string) {
  const [images, setImages] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!reportId) {
      setImages(null);
      return;
    }
    let alive = true;
    setLoading(true);
    api.get<PageImagesResponse>(`/reports/${reportId}/page-images/`)
      .then((r) => { if (alive) setImages(r.pages.map((b64) => `data:image/png;base64,${b64}`)); })
      .catch(() => { if (alive) setImages(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [reportId, refreshKey]);

  return { images, loading };
}
