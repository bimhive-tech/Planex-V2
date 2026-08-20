"use client";

// Live chart previews for the Customize tab canvas — debounced fetch of
// real per-chart SVGs (see chart-svgs-file route + apps/reports/views.py's
// chart_svgs action) so chart elements always show their real rendered
// look. Cheap (no PDF assembly or full-page rasterization, and the report
// context is cached — see _cached_report_context), so this fires on every
// edit instead of needing an explicit refresh.
import { useEffect, useState } from "react";

import type { ChartSvgMap, LayoutElement, LayoutPage } from "@/lib/reportLayout";

const DEBOUNCE_MS = 800;

export interface ChartSvgsState {
  charts: ChartSvgMap;
  /** True once the first real response has landed (or there's nothing to
   * wait for) — lets the canvas grey out chart boxes instead of showing the
   * generic client-side mockup while the real look is still in flight. */
  loaded: boolean;
}

export function useChartSvgs(
  reportId: string | undefined,
  pages: LayoutPage[],
  masterElements: LayoutElement[],
): ChartSvgsState {
  const [charts, setCharts] = useState<ChartSvgMap>({});
  const [loaded, setLoaded] = useState(false);
  const hasChart = pages.some((p) => p.elements.some((e) => e.type === "chart"))
    || masterElements.some((e) => e.type === "chart");

  useEffect(() => {
    if (!reportId || !hasChart) { setLoaded(true); return; }
    let alive = true;
    const timer = setTimeout(() => {
      fetch(`/reports/${reportId}/chart-svgs-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
        }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("chart-svgs fetch failed"))))
        .then((data: { charts: ChartSvgMap }) => { if (alive) setCharts(data.charts); })
        .catch(() => {})
        .finally(() => { if (alive) setLoaded(true); });
    }, DEBOUNCE_MS);
    return () => { alive = false; clearTimeout(timer); };
  }, [reportId, hasChart, pages, masterElements]);

  return { charts, loaded };
}
