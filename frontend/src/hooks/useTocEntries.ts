"use client";

// Live "List of tables/figures/images" content for the Customize tab canvas
// — debounced fetch of real, final-numbered caption lists (see toc-entries-
// file route + apps/reports/views.py's toc_entries action) so a "tables"/
// "figures"/"images" TOC variant shows its real list instead of a "resolved
// in the downloaded PDF" placeholder. Same reasoning as useChartSvgs/
// useTableData: no PDF assembly, and the report context is cached, so this
// is cheap enough to fire on every edit.
import { useEffect, useState } from "react";

import type { LayoutElement, LayoutPage, TocCaptionsData } from "@/lib/reportLayout";

const DEBOUNCE_MS = 800;
const EMPTY: TocCaptionsData = { tables: [], figures: [], images: [] };

export interface TocEntriesState {
  captions: TocCaptionsData;
  /** True once the first real response has landed (or there's nothing to
   * wait for) — mirrors useChartSvgs/useTableData's `loaded`. */
  loaded: boolean;
}

function hasNonContentsToc(pages: LayoutPage[], masterElements: LayoutElement[]): boolean {
  const isNonContents = (e: LayoutElement) =>
    e.type === "toc" && String(e.props.variant ?? "contents") !== "contents";
  return pages.some((p) => p.elements.some(isNonContents)) || masterElements.some(isNonContents);
}

export function useTocEntries(
  reportId: string | undefined,
  pages: LayoutPage[],
  masterElements: LayoutElement[],
): TocEntriesState {
  const [state, setState] = useState<TocEntriesState>({ captions: EMPTY, loaded: false });
  const needed = hasNonContentsToc(pages, masterElements);

  useEffect(() => {
    if (!reportId || !needed) { setState((s) => ({ ...s, loaded: true })); return; }
    let alive = true;
    const timer = setTimeout(() => {
      fetch(`/reports/${reportId}/toc-entries-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
        }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("toc-entries fetch failed"))))
        .then((data: TocCaptionsData) => { if (alive) setState({ captions: data, loaded: true }); })
        .catch(() => { if (alive) setState((s) => ({ ...s, loaded: true })); });
    }, DEBOUNCE_MS);
    return () => { alive = false; clearTimeout(timer); };
  }, [reportId, needed, pages, masterElements]);

  return state;
}
