"use client";

// Live table data for the Customize tab canvas — debounced fetch of real
// per-table header/rows (see table-data-file route + apps/reports/views.py's
// table_data action) so table elements always render actual text, not an
// image. Same reasoning as useChartSvgs: no PDF assembly, and the report
// context is cached, so this is cheap enough to fire on every edit.
import { useEffect, useState } from "react";

import type { LayoutElement, LayoutPage, TableDataMap } from "@/lib/reportLayout";

const DEBOUNCE_MS = 800;

export interface TableDataState {
  tables: TableDataMap;
  /** True once the first real response has landed (or there's nothing to
   * wait for) — lets the canvas grey out table boxes instead of showing the
   * generic client-side mockup while the real look is still in flight. */
  loaded: boolean;
}

export function useTableData(
  reportId: string | undefined,
  pages: LayoutPage[],
  masterElements: LayoutElement[],
): TableDataState {
  const [state, setState] = useState<TableDataState>({ tables: {}, loaded: false });
  const hasTable = pages.some((p) => p.elements.some((e) => e.type === "table"))
    || masterElements.some((e) => e.type === "table");

  useEffect(() => {
    if (!reportId || !hasTable) { setState((s) => ({ ...s, loaded: true })); return; }
    let alive = true;
    const timer = setTimeout(() => {
      fetch(`/reports/${reportId}/table-data-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
        }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("table-data fetch failed"))))
        .then((data: { tables: TableDataMap }) => {
          if (alive) setState({ ...data, loaded: true });
        })
        .catch(() => { if (alive) setState((s) => ({ ...s, loaded: true })); });
    }, DEBOUNCE_MS);
    return () => { alive = false; clearTimeout(timer); };
  }, [reportId, hasTable, pages, masterElements]);

  return state;
}
