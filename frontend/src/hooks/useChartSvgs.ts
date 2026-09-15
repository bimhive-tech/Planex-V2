"use client";

// Live chart previews for the Customize tab canvas — real per-chart SVGs (see
// chart-svgs-file route + apps/reports/views.py's chart_svgs action) so chart
// elements always show their real rendered look.
//
// The first load draws every chart. After that only the charts an edit
// actually touched are redrawn, right away: a resized chart used to wait out
// an 800ms debounce and then a redraw of every chart in the report, so its
// new look arrived seconds after the mouse was released (register D3).
// Moving a chart doesn't change its drawing, so it doesn't redraw at all.
import { useEffect, useRef, useState } from "react";

import type { ChartSvgMap, LayoutElement, LayoutPage, ReportColors, ReportLabels } from "@/lib/reportLayout";

/** Wait before the first, whole-report load — edits made while the page is
 * still settling fold into it. */
const FIRST_LOAD_DEBOUNCE_MS = 800;
/** Wait before redrawing touched charts — just long enough to fold a burst of
 * edits (typing a number) into one request. */
const TOUCHED_DEBOUNCE_MS = 120;

export interface ChartSvgsState {
  charts: ChartSvgMap;
  /** This report's effective label dict — see ReportLabels. Undefined until
   * the first response lands. */
  labels?: ReportLabels;
  /** This report's effective colour scheme — see ReportColors. Undefined
   * until the first response lands. */
  colors?: ReportColors;
  /** True once the first real response has landed (or there's nothing to
   * wait for) — lets the canvas grey out chart boxes instead of showing the
   * generic client-side mockup while the real look is still in flight. */
  loaded: boolean;
}

/** Everything a chart's drawing depends on, per chart element id: its size,
 * its props and its page's repeat setting — not where it sits on the page. */
function chartSignatures(pages: LayoutPage[], masterElements: LayoutElement[]): Map<string, string> {
  const out = new Map<string, string>();
  const add = (el: LayoutElement, repeat: unknown) => {
    if (el.type !== "chart") return;
    out.set(el.id, JSON.stringify({ w: el.w, h: el.h, props: el.props, repeat: repeat ?? null }));
  };
  for (const page of pages) page.elements.forEach((el) => add(el, page.repeat));
  masterElements.forEach((el) => add(el, null));
  return out;
}

export function useChartSvgs(
  reportId: string | undefined,
  pages: LayoutPage[],
  masterElements: LayoutElement[],
): ChartSvgsState {
  const [charts, setCharts] = useState<ChartSvgMap>({});
  const [labels, setLabels] = useState<ReportLabels | undefined>(undefined);
  const [colors, setColors] = useState<ReportColors | undefined>(undefined);
  const [loaded, setLoaded] = useState(false);
  /** Signatures as last requested — what the map is (or will be) drawn for. */
  const requested = useRef<Map<string, string> | null>(null);
  /** Signatures of the draft right now, to discard a response a later edit
   * has already overtaken. */
  const current = useRef<Map<string, string>>(new Map());

  const signatures = chartSignatures(pages, masterElements);
  current.current = signatures;
  const hasChart = signatures.size > 0;

  useEffect(() => {
    if (!reportId || !hasChart) { setLoaded(true); return; }
    const now = current.current;
    const before = requested.current;
    const touched = before ? [...now.keys()].filter((id) => before.get(id) !== now.get(id)) : null;
    if (before) {
      const removed = [...before.keys()].filter((id) => !now.has(id));
      if (removed.length) {
        setCharts((prev) => {
          const next = { ...prev };
          removed.forEach((id) => delete next[id]);
          return next;
        });
      }
    }
    if (touched && touched.length === 0) { requested.current = new Map(now); return; }

    const timer = setTimeout(() => {
      const sent = new Map(current.current);
      requested.current = sent;
      fetch(`/reports/${reportId}/chart-svgs-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
          ...(touched ? { only: touched } : {}),
        }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("chart-svgs fetch failed"))))
        .then((data: { charts: ChartSvgMap; labels: ReportLabels; colors?: ReportColors }) => {
          setCharts((prev) => {
            const next: ChartSvgMap = {};
            // Charts no longer on the draft drop out; the rest keep what they
            // have unless this response is for their current state — a chart
            // edited again while the request was out waits for its own.
            for (const [id, chart] of Object.entries(prev)) {
              if (current.current.has(id)) next[id] = chart;
            }
            for (const [id, chart] of Object.entries(data.charts)) {
              if (current.current.get(id) === sent.get(id)) next[id] = chart;
            }
            return next;
          });
          setLabels(data.labels);
          setColors(data.colors);
        })
        .catch(() => {
          // Let the next edit retry these charts rather than treating them as drawn.
          if (touched && requested.current === sent) touched.forEach((id) => sent.delete(id));
        })
        .finally(() => setLoaded(true));
    }, touched ? TOUCHED_DEBOUNCE_MS : FIRST_LOAD_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `pages`/`masterElements` identity is the trigger; the signatures decide
    // whether anything chart-related actually changed.
  }, [reportId, hasChart, pages, masterElements]);

  return { charts, labels, colors, loaded };
}
