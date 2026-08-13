"use client";

// Live table previews for the Customize tab canvas — debounced fetch of
// real per-table PNGs (see table-images-file route + apps/reports/views.py's
// table_images action) so table elements always show their real rendered
// look. Same reasoning as useChartSvgs: no PDF assembly or full-page
// rasterization, and the report context is cached, so this is cheap enough
// to fire on every edit.
import { useEffect, useState } from "react";

import type { LayoutElement, LayoutPage, TableImageMap } from "@/lib/reportLayout";

const DEBOUNCE_MS = 800;

export function useTableImages(
  reportId: string | undefined,
  pages: LayoutPage[],
  masterElements: LayoutElement[],
): TableImageMap {
  const [tables, setTables] = useState<TableImageMap>({});
  const hasTable = pages.some((p) => p.elements.some((e) => e.type === "table"))
    || masterElements.some((e) => e.type === "table");

  useEffect(() => {
    if (!reportId || !hasTable) return;
    let alive = true;
    const timer = setTimeout(() => {
      fetch(`/reports/${reportId}/table-images-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
        }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("table-images fetch failed"))))
        .then((data: { tables: TableImageMap }) => { if (alive) setTables(data.tables); })
        .catch(() => {});
    }, DEBOUNCE_MS);
    return () => { alive = false; clearTimeout(timer); };
  }, [reportId, hasTable, pages, masterElements]);

  return tables;
}
