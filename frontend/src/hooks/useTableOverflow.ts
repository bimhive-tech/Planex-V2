"use client";

// Live table-continuation data for the Customize tab canvas — debounced
// fetch of the real extra rows a table sheds onto continuation pages in
// the download (see table-overflow-file route + apps/reports/views.py's
// table_overflow action, which reuses the exact ReportLab `Table.split()`
// calls the real PDF's own overflow pagination uses). Consumed by
// buildOverflowPages to synthesize real, viewable continuation pages in
// the editor's own page list instead of just clipping the box — see
// ElementPreview's OverflowClip for the fallback when this hasn't loaded
// yet or a table's overflow genuinely doesn't need extra pages.
import { useEffect, useState } from "react";

import type { LayoutElement, LayoutPage, TableOverflowMap } from "@/lib/reportLayout";

const DEBOUNCE_MS = 800;

export interface TableOverflowState {
  continuations: TableOverflowMap;
  /** True once the first real response has landed (or there's nothing to
   * wait for) — mirrors useChartSvgs/useTableData/useTocEntries' `loaded`. */
  loaded: boolean;
}

export function useTableOverflow(
  reportId: string | undefined,
  pages: LayoutPage[],
  masterElements: LayoutElement[],
): TableOverflowState {
  const [state, setState] = useState<TableOverflowState>({ continuations: {}, loaded: false });
  const hasTable = pages.some((p) => p.elements.some((e) => e.type === "table"))
    || masterElements.some((e) => e.type === "table");

  useEffect(() => {
    if (!reportId || !hasTable) { setState((s) => ({ ...s, loaded: true })); return; }
    let alive = true;
    const timer = setTimeout(() => {
      fetch(`/reports/${reportId}/table-overflow-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
        }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("table-overflow fetch failed"))))
        .then((data: { continuations: TableOverflowMap }) => {
          if (alive) setState({ continuations: data.continuations, loaded: true });
        })
        .catch(() => { if (alive) setState((s) => ({ ...s, loaded: true })); });
    }, DEBOUNCE_MS);
    return () => { alive = false; clearTimeout(timer); };
  }, [reportId, hasTable, pages, masterElements]);

  return state;
}
