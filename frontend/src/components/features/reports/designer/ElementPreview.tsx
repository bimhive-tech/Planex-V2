"use client";

// How each element type looks on the canvas. When liveData is available (the
// report-level "Customize" tab — see ReportLayoutEditor), tables/charts/
// fields/images show this project's actual content instead of generic
// placeholders, so editing looks like editing the real thing. pinnedItem is
// the specific zone/photo/etc. an expanded repeating page was pinned to (see
// reportRepeat.ts), letting item.* bindings resolve too. In the project-
// agnostic Template Builder both are undefined and every element falls back
// to the representative placeholder it always showed.
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { RichTextEditor, type RichTextEditorHandle } from "@/components/ui/RichTextEditor";
import { Skeleton } from "@/components/ui/Skeleton";
import { CHART_SOURCES, FIELD_SOURCES, TABLE_SOURCES } from "@/lib/reportElements";
import type {
  ChartSvgMap, CustomTableData, LayoutElement, ReportLabels, TableDataMap, TableStyle, TocCaptionsData, TocEntry,
} from "@/lib/reportLayout";
import { resolveItemField } from "@/lib/reportRepeat";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { CustomTableEditor } from "./CustomTableEditor";
import { DescriptionEmbedToolbar } from "../DescriptionEmbedToolbar";
import styles from "./designer.module.css";

interface PreviewProps {
  el: LayoutElement;
  /** mm-to-px factor for this canvas (BASE_SCALE * zoom, see LayoutEditor) —
   * text/field font sizes are converted through this so they resize in step
   * with the element's box as you zoom. Without it, a box drawn at
   * `w * scale` grows and shrinks with zoom while a plain CSS `pt` font size
   * doesn't, so the same text wraps onto a different number of lines at
   * different zoom levels purely from the mismatch, not any real change. */
  scale: number;
  liveData?: ReportData | null;
  /** This report's id — lets a description element's inline image-embed
   * control attach an upload to this report. Undefined in the project-
   * agnostic Template Builder, where the image-embed button is hidden. */
  reportId?: string;
  pinnedItem?: RepeatItem | RepeatItem[] | null;
  /** Live, real per-chart previews (see useChartSvgs) — the same Drawing
   * the real PDF renders for this exact chart, exported to SVG. Present
   * only in the report Customize tab; a chart element falls back to the
   * approximate client-side mockup below until its entry lands (briefly,
   * on first load) or when there's no reportId at all (Template Builder,
   * which has no real project data for a chart to match anyway). */
  chartSvgs?: ChartSvgMap;
  /** Live, real per-table data — see useTableData. Same fallback reasoning
   * as chartSvgs above. Each entry carries its own effective style (colors,
   * font size, padding — the report's defaults patched by this element's
   * own props.style, if it has one), not a separate shared prop. */
  tableData?: TableDataMap;
  /** False until chartSvgs/tableData's first real response has landed —
   * chart/table boxes show a neutral grey skeleton instead of the generic
   * client-side mockup, so a still-loading canvas never reads as if it's
   * already showing real content. Defaults true (Template Builder, where
   * chartSvgs/tableData never load at all — the mockup is the only look). */
  previewsReady?: boolean;
  /** Every page in the current draft, in order, with its real page number
   * — see ReportConfigurator, which computes this once from `pages`.
   * Present in both the report Customize tab and the Template Builder
   * (it only needs the page list, not real project data), so a "toc"
   * element never falls back to a sample list. */
  tocEntries?: TocEntry[];
  /** Live, real "List of tables/figures/images" content — see
   * useTocEntries. Present only in the report Customize tab; a "tables"/
   * "figures"/"images" TOC variant falls back to its "resolved in the
   * downloaded PDF" placeholder in the Template Builder, which has no real
   * project data to number captions against. */
  tocCaptions?: TocCaptionsData;
  /** This report's effective label dict (cfg["labels"]) — see useChartSvgs/
   * useTableData. A table/chart element's title/caption falls back to this
   * (the same dict _table_or_chart_title/_collect_captions read on the
   * backend) when it has no title_text/caption of its own, so an
   * un-overridden element's fallback text matches the real PDF exactly
   * instead of showing the English source-picker label. Undefined outside
   * the report Customize tab (Template Builder — falls back further, to
   * CHART_SOURCES/TABLE_SOURCES, since there's no real report to derive an
   * effective config from). */
  labels?: ReportLabels;
  /** The page this element is being drawn on — a toc element skips its
   * own page, mirroring pdf_canvas._draw_toc_element. */
  ownPageId?: string;
  /** Commits an inline text edit (double-click a table cell, TOC row,
   * field value, or plain text box directly on the canvas) — see
   * CanvasPage's doc comment. Undefined outside the report Customize tab
   * (the Template Builder has no real project data to override) and for
   * ghost/master-as-background elements. */
  onElementChange?: (el: LayoutElement) => void;
}

/** 1pt = 1/72in = 25.4/72mm — matches how apps/reports/pdf_canvas.py's
 * `_text_style` treats `props.size` (a ReportLab `fontSize`, i.e. points),
 * so the preview's line-wrapping tracks the real PDF's, not just itself
 * across zoom levels. */
const PT_TO_MM = 25.4 / 72;
function ptToPx(pt: number, scale: number): number {
  return pt * PT_TO_MM * scale;
}

function label(list: { value: string; label: string }[], value: unknown, fallback: string) {
  return list.find((o) => o.value === value)?.label ?? fallback;
}

/** A table/chart's title/caption fallback text — the real `labels` dict
 * (this report's effective cfg["labels"], same as _table_or_chart_title/
 * _collect_captions read on the backend) when it's loaded, else the
 * English source-picker `list` label (Template Builder, or before the
 * first live response lands). Keeps the canvas's fallback text the same
 * language/wording the download will actually show instead of a
 * design-time-only English placeholder. */
function sourceLabel(labels: Record<string, string> | undefined, list: { value: string; label: string }[], value: unknown, fallback: string) {
  const source = String(value ?? "");
  return labels?.[source] ?? label(list, value, fallback);
}

/** Mirrors pdf_canvas.py's _draw_image_border exactly — opt-in via
 * props.border, same color/width. Undefined (not `border: "none"`) when
 * off, so it doesn't override the CSS class's own box-sizing. */
function imageBorderStyle(props: Record<string, unknown>): React.CSSProperties | undefined {
  if (!props.border) return undefined;
  const width = Number(props.border_width ?? 0.3);
  const color = String(props.border_color ?? "#000000");
  return { border: `${width}mm solid ${color}`, boxSizing: "border-box" };
}

/** Mirrors pdf_layout.py's draw_fitted_image exactly — an "image" element's
 * `fit` (cover/contain) and `focal_x`/`focal_y` crop-offset props, via the
 * browser's own native `object-fit`/`object-position` (identical math to
 * what draw_fitted_image derives by hand for ReportLab, since CSS
 * object-position is precisely "which point of the image lands at which
 * point of the box"). Previously always contain, regardless of `fit` — the
 * "Cover" option existed in the Properties panel but nothing behind it
 * read it, on this side or the real PDF's. */
function imageFitStyle(props: Record<string, unknown>): React.CSSProperties {
  const fit = props.fit === "cover" ? "cover" : "contain";
  const focalX = Number(props.focal_x ?? 50);
  const focalY = Number(props.focal_y ?? 50);
  return { objectFit: fit, objectPosition: `${focalX}% ${focalY}%` };
}

/** item.* sources bind to one item, never a chunk group. */
function singleItem(pinnedItem: RepeatItem | RepeatItem[] | null | undefined): RepeatItem | null {
  if (!pinnedItem) return null;
  return Array.isArray(pinnedItem) ? (pinnedItem[0] ?? null) : pinnedItem;
}

/** Double-click any live/computed piece of text on the canvas — a table
 * cell, a TOC row's name, a field's resolved value, a plain text box — to
 * edit it directly, Canva-style. Committing calls `onCommit`, which the
 * caller wires to the exact override the real PDF also applies (see
 * pdf_tables.apply_table_overrides / pdf_canvas._draw_toc_element /
 * _draw_field's docstrings) — never just a cosmetic canvas-only change.
 * `undefined` `onCommit` (outside the report Customize tab, where there's
 * no real project data to override in the first place) falls back to
 * plain, non-editable text. */
function InlineEditableText({
  value, onCommit, className, dir, style,
}: {
  value: string;
  onCommit?: (next: string) => void;
  className?: string;
  dir?: "ltr" | "rtl";
  style?: React.CSSProperties;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  useEffect(() => {
    if (editing) { inputRef.current?.focus(); inputRef.current?.select(); }
  }, [editing]);

  if (!onCommit) {
    return <span className={className} style={style} dir={dir}>{value}</span>;
  }

  function commit() {
    setEditing(false);
    if (draft !== value) onCommit!(draft);
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        className={`${styles.inlineEditInput} ${className ?? ""}`}
        style={style}
        dir={dir}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(); }
          if (e.key === "Escape") { e.preventDefault(); setDraft(value); setEditing(false); }
        }}
        onPointerDown={(e) => e.stopPropagation()}
      />
    );
  }

  return (
    <span
      className={className}
      style={style}
      dir={dir}
      onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
    >
      {value}
    </span>
  );
}

const fmtDate = (d: string | null) => (d ? new Date(d).toLocaleDateString(undefined, { day: "2-digit", month: "short" }) : "—");
const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(0)}%`);

const money = (v: string | number | null | undefined, currency: string) =>
  v ? `${Number(v).toLocaleString()} ${currency}` : "";

/** Every row apps/reports/pdf_canvas.py's resolve_table() draws for
 * "project_info", in the same order — this preview should show the same
 * fields the real PDF does, not a shortened summary of them. */
function projectInfoRows(data: ReportData): string[][] {
  const p = data.project;
  const dur = data.duration;
  const rows: [string, string][] = [
    ["Name", p.name], ["Code", p.code ?? ""], ["Client", p.client],
    ["Consultant", p.consultant], ["Contractor", p.contractor], ["Type", p.type],
    ["Location", p.location], ["Value", money(p.budget, p.budget_currency ?? p.currency)],
    ["Contract value", money(p.contract_value, p.contract_value_currency ?? p.currency)],
    ["Approved value", money(p.approved_value, p.approved_value_currency ?? p.currency)],
    ["Forecast cost", money(p.forecast_cost, p.forecast_cost_currency ?? p.currency)],
    ["Duration", dur?.total ? `${dur.total} days` : ""],
    ["Start", fmtDate(p.planned_start)], ["Finish", fmtDate(p.planned_finish)],
    ["Revised finish", p.revised_finish ? fmtDate(p.revised_finish) : ""],
    ["Forecast finish", p.forecast_finish ? fmtDate(p.forecast_finish) : ""],
    ["Delay", dur?.delay ? `${dur.delay} days` : ""],
    ["Size", p.size_sqm ? `${Number(p.size_sqm).toLocaleString()} m²` : ""],
  ];
  return rows.filter(([, v]) => v);
}

/** Real row cells for a table source, or null when there's no live data (or
 * nothing to show) for it — the caller falls back to placeholder bars. Shows
 * every real row the actual PDF would, not a shortened preview of them. */
function realTableRows(source: unknown, data: ReportData | null | undefined, pinnedItem: RepeatItem | RepeatItem[] | null | undefined): string[][] | null {
  if (source === "item.children") {
    const children = (singleItem(pinnedItem)?.children as { name: string; actual: number | null }[]) || [];
    return children.length ? children.map((c) => [c.name, fmtPct(c.actual)]) : null;
  }
  if (!data) return null;
  switch (source) {
    case "project_info": {
      const rows = projectInfoRows(data);
      return rows.length ? rows : null;
    }
    case "zone_progress":
      return data.zones.length ? data.zones.map((z) => [z.name, fmtPct(z.progress)]) : null;
    case "hierarchy_progress":
      return data.hierarchy.length
        ? data.hierarchy.map((h) => [h.name, fmtPct(h.actual)]) : null;
    case "discipline_progress":
      return data.discipline.length
        ? data.discipline.map((d) => [d.name, fmtPct(d.concrete)]) : null;
    case "progress_compare": {
      const rows = data.zones.filter((z) => z.planned != null);
      return rows.length ? rows.map((z) => [z.name, fmtPct(z.planned), fmtPct(z.progress)]) : null;
    }
    case "critical_path_delays":
      return data.critical_path.length
        ? data.critical_path.map((r) => [r.name, `${r.delay_days}d`]) : null;
    case "activity_schedule":
      return data.activity_schedule.length
        ? data.activity_schedule.map((r) => [
            r.name, r.original_duration ?? "—", r.actual_duration ?? "—",
            r.schedule_performance_index ?? "—",
          ].map(String))
        : null;
    case "milestones":
      return data.milestones.length
        ? data.milestones.map((m) => [m.title, fmtDate(m.date)]) : null;
    case "invoices":
      return data.invoices.length
        ? data.invoices.map((i) => [i.name, i.value.toLocaleString()]) : null;
    case "submittals":
      return data.submittals.rows.length
        ? data.submittals.rows.map((s) => [s.title, s.status]) : null;
    case "delays":
      return data.delays.length
        ? data.delays.map((d) => [d.title, `${d.impact_days}d`]) : null;
    default:
      return null; // detailed_progress — the real grid is heavy and not sent to the builder
  }
}

/** Same Arabic-detection heuristic as apps/reports/pdf_base.py's has_arabic
 * — picks each cell's own reading direction; the text always renders as
 * received either way. Declared once, shared by every live-data preview
 * (table cells here, TOC rows further down). */
const ARABIC_RE = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;

function TableCell({ text, onCommit }: { text: string; onCommit?: (next: string) => void }) {
  return <InlineEditableText value={text} onCommit={onCommit} dir={ARABIC_RE.test(text) ? "rtl" : "ltr"} />;
}

/** A data-bound table's `live.rows` already has hidden rows filtered out
 * server-side (see apps/reports/pdf_tables.py's apply_table_overrides) — but
 * `overrides`/`hidden_rows` keys both refer to the row's *original*,
 * pre-filter position. This reconstructs that original index for each
 * displayed row (in order, skipping whatever's already hidden) so an edit
 * or a new hide made after an earlier row was hidden still lands on the
 * right row instead of silently shifting by one. */
function originalRowIndices(count: number, hiddenRows: number[] | undefined): number[] {
  const hidden = new Set(hiddenRows ?? []);
  const out: number[] = [];
  let k = 0;
  for (let n = 0; n < count; n++) {
    while (hidden.has(k)) k++;
    out.push(k);
    k++;
  }
  return out;
}

/** The small "×" gutter cell that hides a data-bound table's row from this
 * report's view (see TablePreview's commitHideRow) — a real table cell so it
 * lines up with the header/body rows around it, not an absolutely
 * positioned overlay. */
function RowHideButton({ onHide }: { onHide: () => void }) {
  return (
    <td className={styles.tableLiveRowHandle}>
      <button
        type="button"
        className={styles.tableLiveRowHideBtn}
        onClick={onHide}
        onPointerDown={(e) => e.stopPropagation()}
        aria-label="Hide this row"
      >
        <Icon name="close" size={10} />
      </button>
    </td>
  );
}

/** Mirrors pdf_tables.py's _pct_or_dash exactly (one decimal place, an
 * em-dash for a missing value) — hierarchy rows are numbers, not
 * pre-formatted strings, unlike every other table kind. */
const fmtPctOrDash = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`);

/** CSS custom properties, not literal colors — the one CLAUDE.md-sanctioned
 * use of inline style, since these values are genuinely dynamic (the real
 * PDF's own per-report color scheme, from cfg["colors"]/cfg["table"] — see
 * table_data's docstring), not something a stylesheet could hardcode. */
function tableStyleVars(style: TableStyle | null | undefined): React.CSSProperties {
  return {
    "--tableBorder": style?.border ? (style?.border_color ?? "#000000") : "transparent",
    "--tableHeaderBg": style?.header_bg ?? "#1F4E79",
    "--tableHeaderText": style?.header_text ?? "#ffffff",
    "--tableZebra": style?.zebra_color ?? "#eef3f8",
    "--tableFontSize": `${style?.font_size ?? 8}px`,
    "--tableCellPadding": `${style?.cell_padding ?? 3}px`,
  } as React.CSSProperties;
}

/** Clips live content to its element's own box instead of letting something
 * too tall for it (a table with more rows than fit, or a description with
 * more content than fits) spill past it — previously it grew right past the
 * box, past the page, off the bottom of the paper. The real PDF now
 * genuinely continues either kind onto extra pages (see apps/reports/
 * pdf_canvas.py's _expand_table_overflow / _expand_description_overflow);
 * the canvas doesn't synthesize matching extra pages into the editor's own
 * page list (a much bigger UI change — phantom pages the user never
 * created), so this shows what fits and says so, rather than either
 * spilling or silently cutting content with no indication anything's
 * missing. */
function OverflowClip({ children, note = "More rows than fit here — continues in the downloaded PDF" }: {
  children: React.ReactNode; note?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    setOverflowing(node.scrollHeight > node.clientHeight + 1);
  });

  return (
    <div ref={ref} className={styles.tableClip}>
      {children}
      {overflowing && <div className={styles.tableOverflowNote}>{note}</div>}
    </div>
  );
}

function TablePreview({ el, liveData, pinnedItem, tableData, previewsReady = true, labels, onElementChange }: PreviewProps) {
  const p = el.props;

  // "custom" — no backend data source at all; it's built by hand or pasted
  // from Excel (see CustomTableEditor) — checked *before* the live-data
  // block below, since a custom table's own resolve_table branch still
  // returns a resolvable "ok" table from its seed data, which would
  // otherwise make the live read-only view win here too. Edited directly on
  // the canvas: real <input> cells, add/remove row/column controls, right
  // on the page instead of tucked in the Properties panel.
  if (p.source === "custom" && onElementChange) {
    return (
      <CustomTableEditor
        data={p.custom_data as CustomTableData | undefined}
        onChange={(custom_data) => onElementChange({ ...el, props: { ...p, custom_data } })}
      />
    );
  }

  // The real thing — the exact same header/rows resolve_table computes for
  // the real PDF table (see useTableData/apps/reports/views.py's table_data,
  // raw=True mode), rendered as a genuine HTML table: real, selectable text,
  // not an image of any kind. Falls through to the client-side mockup below
  // only while this hasn't landed yet or outside the report Customize tab.
  const live = tableData?.[el.id];
  // The report Customize tab, but the first real response hasn't landed yet
  // — a neutral grey skeleton, not the generic mockup below (which would
  // otherwise be mistaken for this element's actual real content).
  if (!live && !previewsReady) {
    return <Skeleton width="100%" height="100%" radius="var(--radius-sm)" />;
  }

  // A double-clicked cell writes into props.overrides, keyed `hc{col}` for
  // a header cell and `r{row}c{col}` for a body cell — the exact same keys
  // pdf_tables.apply_table_overrides reads, so this edit reaches the real
  // downloaded PDF too (see resolve_table's docstring), not just this
  // preview. Undefined when there's nowhere to commit to (Template
  // Builder) — InlineEditableText then renders plain, non-editable text.
  const commitCell = onElementChange
    ? (key: string, value: string) => {
        const overrides = { ...(p.overrides as Record<string, string> | undefined), [key]: value };
        onElementChange({ ...el, props: { ...p, overrides } });
      }
    : undefined;

  // A clicked row's "×" writes into props.hidden_rows — a data-bound table's
  // rows come from real project data and can't be deleted the way a custom
  // table's can, but a report author can still drop specific ones from this
  // one report's view. pdf_tables.apply_table_overrides reads the same prop
  // to filter it out of the downloaded PDF too, so this is never just a
  // canvas-only trick. Undefined for "custom" tables — those rows are
  // deleted for real instead (see the CustomTableEditor branch below).
  const hiddenRows = p.hidden_rows as number[] | undefined;
  const commitHideRow = onElementChange && p.source !== "custom"
    ? (originalIndex: number) => {
        onElementChange({ ...el, props: { ...p, hidden_rows: [...(hiddenRows ?? []), originalIndex] } });
      }
    : undefined;

  if (live) {
    if (live.status !== "ok") {
      const name = sourceLabel(labels, TABLE_SOURCES, p.source, String(p.source ?? ""));
      return <div className={styles.chartPlaceholder}>{`${name} — no data for this project yet`}</div>;
    }
    const vars = tableStyleVars(live.style);
    // live.rows already has hidden rows filtered out server-side — recover
    // each displayed row's real original index (see originalRowIndices) so
    // overrides/hidden_rows keys stay in the same index space as the data
    // actually came from, not the shorter post-filter list.
    const rowIdx = originalRowIndices(live.rows.length, hiddenRows);

    if (live.kind === "info") {
      return (
        <OverflowClip>
          <table className={styles.tableLive} data-kind="info" style={vars}>
            <tbody>
              {live.rows.map(([labelText, valueText], i) => {
                const oi = rowIdx[i];
                return (
                  <tr key={i}>
                    {commitHideRow && <RowHideButton onHide={() => commitHideRow(oi)} />}
                    <td className={styles.tableLiveInfoLabel}>
                      <TableCell text={labelText} onCommit={commitCell && ((v) => commitCell(`r${oi}c0`, v))} /> •
                    </td>
                    <td className={styles.tableLiveInfoValue}>
                      <TableCell text={valueText} onCommit={commitCell && ((v) => commitCell(`r${oi}c1`, v))} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </OverflowClip>
      );
    }

    if (live.kind === "hierarchy") {
      return (
        <OverflowClip>
          <table className={styles.tableLive} data-kind="hierarchy" style={vars}>
            <thead>
              <tr>
                {commitHideRow && <th className={styles.tableLiveRowHandle} />}
                {live.header.map((h, i) => (
                  <th key={i}><TableCell text={h} onCommit={commitCell && ((v) => commitCell(`hc${i}`, v))} /></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {live.rows.map((row, i) => {
                const oi = rowIdx[i];
                return (
                  <tr key={i} data-zone={row.level === 0 ? "on" : undefined}>
                    {commitHideRow && <RowHideButton onHide={() => commitHideRow(oi)} />}
                    <td className={row.level === 0 ? styles.tableLiveZoneName : undefined}>
                      <span className={row.level === 1 ? styles.tableLiveIndent : undefined}>
                        <TableCell text={row.name} onCommit={commitCell && ((v) => commitCell(`r${oi}c0`, v))} />
                      </span>
                    </td>
                    <td data-align="center">
                      <TableCell text={fmtPctOrDash(row.actual)} onCommit={commitCell && ((v) => commitCell(`r${oi}c1`, v))} />
                    </td>
                    <td data-align="center">
                      <TableCell text={fmtPctOrDash(row.previous)} onCommit={commitCell && ((v) => commitCell(`r${oi}c2`, v))} />
                    </td>
                    <td data-align="center">
                      <TableCell text={fmtPctOrDash(row.planned)} onCommit={commitCell && ((v) => commitCell(`r${oi}c3`, v))} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </OverflowClip>
      );
    }

    // "data" — a plain header + flat rows grid (zone_progress, milestones,
    // invoices, etc.).
    return (
      <OverflowClip>
        <table className={styles.tableLive} data-kind="data" style={vars}>
          <thead>
            <tr>
              {commitHideRow && <th className={styles.tableLiveRowHandle} />}
              {live.header.map((h, i) => (
                <th key={i}><TableCell text={h} onCommit={commitCell && ((v) => commitCell(`hc${i}`, v))} /></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {live.rows.map((row, i) => {
              const oi = rowIdx[i];
              return (
                <tr key={i} data-zebra={live.style.zebra && i % 2 === 1 ? "on" : undefined}>
                  {commitHideRow && <RowHideButton onHide={() => commitHideRow(oi)} />}
                  {row.map((cell, j) => (
                    <td key={j} data-align="center">
                      <TableCell text={cell} onCommit={commitCell && ((v) => commitCell(`r${oi}c${j}`, v))} />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </OverflowClip>
    );
  }

  // Report Customize tab (tableData present) but this element got no entry
  // back and loading has finished — the request failed. Say so rather than
  // dropping to the mockup below, which draws a convincing empty grid for a
  // table that may print blank. "custom" is exempt: it has no backend data
  // behind it, so it legitimately never appears in tableData (2026-08-30).
  if (tableData && p.source !== "custom") {
    return <div className={styles.chartPlaceholder}>Couldn&apos;t load this table&apos;s data — retry in a moment</div>;
  }

  const headerBg = String(p.header_bg ?? "#1F4E79");
  const headerText = String(p.header_text ?? "#ffffff");
  // "custom" has no backend data behind it (it's authored directly in the
  // Properties panel — see CustomTableEditor) so it renders here straight
  // from props, not through realTableRows/liveData like every other source.
  const customData = p.source === "custom" ? (p.custom_data as CustomTableData | undefined) : undefined;
  const real = customData
    ? (customData.rows.length ? customData.rows : null)
    : realTableRows(p.source, liveData, pinnedItem);
  return (
    <div className={styles.tablePreview}>
      <div className={styles.tablePreviewHead} style={{ background: headerBg, color: headerText }}>
        {label(TABLE_SOURCES, p.source, "Table")}
      </div>
      {real
        ? real.map((cells, i) => (
            <div key={i} className={styles.tablePreviewRow} data-zebra={p.zebra && i % 2 === 1 ? "on" : undefined}>
              {cells.map((c, j) => (
                <span key={j} className={styles.tablePreviewCell} data-align={j > 0 ? "right" : undefined}>{c}</span>
              ))}
            </div>
          ))
        : [0, 1, 2, 3].map((i) => (
            <div key={i} className={styles.tablePreviewRow} data-zebra={p.zebra && i % 2 === 1 ? "on" : undefined}>
              <span /><span /><span />
            </div>
          ))}
    </div>
  );
}

/** Bar heights (0-100) for a bar/column chart source, or null to fall back. */
function realBarHeights(source: unknown, data: ReportData | null | undefined, pinnedItem: RepeatItem | RepeatItem[] | null | undefined): number[] | null {
  if (source === "item.units") {
    const children = (singleItem(pinnedItem)?.children as { actual: number | null }[]) || [];
    return children.length ? children.slice(0, 5).map((c) => c.actual ?? 0) : null;
  }
  if (!data) return null;
  if (source === "zone_progress" && data.zones.length) return data.zones.slice(0, 5).map((z) => z.progress);
  if (source === "area_progress" && data.areas.length) return data.areas.slice(0, 5).map((a) => a.actual ?? 0);
  if (source === "cashflow_monthly" && data.cashflow.length) {
    const max = Math.max(1, ...data.cashflow.map((c) => Math.max(c.planned, c.actual)));
    return data.cashflow.slice(0, 5).map((c) => (c.actual / max) * 100);
  }
  return null;
}

/** Line points (0-100 y-values) for a line/area chart source, or null. */
function realLinePoints(source: unknown, data: ReportData | null | undefined): number[] | null {
  if (!data) return null;
  if (source === "scurve" && data.scurve.length) return data.scurve.map((s) => s.actual);
  if (source === "cashflow_cumulative" && data.cashflow.length) {
    const max = Math.max(1, data.cashflow[data.cashflow.length - 1]?.cum_actual ?? 1);
    return data.cashflow.map((c) => (c.cum_actual / max) * 100);
  }
  return null;
}

function polyline(values: number[], invert = true): string {
  if (values.length < 2) return "";
  const step = 100 / (values.length - 1);
  return values.map((v, i) => `${(i * step).toFixed(1)},${invert ? 40 - v * 0.4 : v * 0.4}`).join(" ");
}

// Matches the 4-zone Poor/Average/Good/Excellent band colors the PDF's real
// speedometer_chart draws (see pdf_charts.py) — sampled from the reference
// dashboard's own SPI gauge, not an arbitrary placeholder palette.
const GAUGE_BANDS = [
  { from: 0, to: 25, color: "#B40000" },
  { from: 25, to: 50, color: "#FFC000" },
  { from: 50, to: 75, color: "#FFFF00" },
  { from: 75, to: 100, color: "#77933C" },
] as const;

function gaugeArcPoint(pct: number): [number, number] {
  const rad = ((180 - (pct / 100) * 180) * Math.PI) / 180;
  return [18 + 16 * Math.cos(rad), 18 - 16 * Math.sin(rad)];
}

function GaugeSvg({ value, color, showLabel = true }: { value: number; color: string; showLabel?: boolean }) {
  const pct = Math.max(0, Math.min(100, value));
  const angle = -90 + (pct / 100) * 180;
  const needle = [18 + 13 * Math.cos((angle * Math.PI) / 180), 18 + 13 * Math.sin((angle * Math.PI) / 180)];
  return (
    <svg viewBox="0 0 36 22" className={styles.chartSvg} aria-hidden="true">
      {GAUGE_BANDS.map((band) => {
        const [x0, y0] = gaugeArcPoint(band.from);
        const [x1, y1] = gaugeArcPoint(band.to);
        return (
          <path
            key={band.from}
            d={`M${x0.toFixed(2)} ${y0.toFixed(2)} A16 16 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`}
            fill="none" stroke={band.color} strokeWidth="4" strokeLinecap="butt"
          />
        );
      })}
      <line x1="18" y1="18" x2={needle[0]} y2={needle[1]} stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="18" cy="18" r="1.5" fill={color} />
      {showLabel && <text x="18" y="21.5" fontSize="4" textAnchor="middle" fill={color}>{pct.toFixed(0)}%</text>}
    </svg>
  );
}

function DonutSvg({ frac, colorA, colorB, hollow }: { frac: number; colorA: string; colorB: string; hollow: boolean }) {
  const clamped = Math.max(0, Math.min(1, frac));
  const angle = clamped * 360;
  const rad = ((angle - 90) * Math.PI) / 180;
  const [x, y] = [18 + 16 * Math.cos(rad), 18 + 16 * Math.sin(rad)];
  const large = angle > 180 ? 1 : 0;
  return (
    <svg viewBox="0 0 36 36" className={styles.chartSvg} aria-hidden="true">
      <circle cx="18" cy="18" r="16" fill={colorB} />
      {angle > 0 && (
        <path d={`M18 18 L18 2 A16 16 0 ${large} 1 ${x} ${y} Z`} fill={colorA} />
      )}
      {hollow && <circle cx="18" cy="18" r="8" fill="#fff" />}
    </svg>
  );
}

/** A real gauge value (0-100), or null when this specific binding has no
 * real data to show (e.g. a zone with no schedule of its own) — the caller
 * falls back to the plain placeholder rather than a fake-looking value, so
 * "no data" never gets mistaken for a real (if unremarkable) reading. */
function realGaugeValue(source: unknown, liveData: ReportData | null | undefined, item: RepeatItem | null): number | null {
  if (source === "item.spi") {
    const v = item?.progress ?? item?.actual;
    return typeof v === "number" ? v : null;
  }
  if (source === "spi") return liveData?.overall ?? null;
  return null;
}

/** A real donut/pie fraction (0-1), or null — see realGaugeValue. */
function realDonutFrac(source: unknown, liveData: ReportData | null | undefined, item: RepeatItem | null): number | null {
  if (source === "item.duration") {
    const dur = item?.duration as { elapsed: number; total: number } | null | undefined;
    return dur?.total ? dur.elapsed / dur.total : null;
  }
  if (source === "breakdown") {
    return liveData?.breakdown.total ? liveData.breakdown.completed / liveData.breakdown.total : null;
  }
  if (source === "duration") {
    return liveData?.duration?.total ? liveData.duration.elapsed / liveData.duration.total : null;
  }
  return null;
}

function ChartPreview({ el, liveData, pinnedItem, chartSvgs, previewsReady = true, labels }: PreviewProps) {
  const p = el.props;
  const type = String(p.chart_type ?? "column");
  const source = p.source;
  const a = String(p.color_a ?? "#4F81BD");
  const b = String(p.color_b ?? "#C0504D");
  const item = singleItem(pinnedItem);

  // The real thing — same Drawing the PDF itself renders for this exact
  // chart (see useChartSvgs/apps/reports/views.py's chart_svgs), not an
  // approximation. Falls through to the client-side mockup below only
  // while this hasn't landed yet (briefly, on first load) or outside the
  // report Customize tab (chartSvgs is undefined there — no real project
  // data for a chart to match in the first place).
  const live = chartSvgs?.[el.id];
  // The report Customize tab, but the first real response hasn't landed yet
  // — grey skeleton, not the generic mockup (see TablePreview's same check).
  if (!live && !previewsReady) {
    return <Skeleton width="100%" height="100%" radius="var(--radius-sm)" />;
  }
  if (live) {
    if (live.status === "ok") {
      return (
        <div className={styles.chartSvgLive} dangerouslySetInnerHTML={{ __html: live.svg }} />
      );
    }
    const name = sourceLabel(labels, CHART_SOURCES, source, String(source ?? ""));
    const message = live.status === "too_small"
      ? `${name} — box too small to draw this chart`
      : `${name} — no data for this project yet`;
    return <div className={styles.chartPlaceholder}>{message}</div>;
  }

  // Report Customize tab (chartSvgs present) but this element got no entry
  // back and loading has finished — the request failed. Say so. Falling
  // through to the mockup below would draw plausible fake bars for a chart
  // that may well print blank, which is the one thing this canvas must never
  // do (2026-08-30). The Template Builder has no chartSvgs at all and keeps
  // the mockup, which is all it can honestly show.
  if (chartSvgs) {
    return <div className={styles.chartPlaceholder}>Couldn&apos;t load this chart&apos;s preview — retry in a moment</div>;
  }

  let body: React.ReactNode;
  if (type === "gauge") {
    const real = realGaugeValue(source, liveData, item);
    body = <GaugeSvg value={real ?? 65} color={real != null ? a : "var(--border-strong)"} showLabel={real != null} />;
  } else if (type === "pie" || type === "donut") {
    const real = realDonutFrac(source, liveData, item);
    body = real != null
      ? <DonutSvg frac={real} colorA={a} colorB={b} hollow={type === "donut"} />
      : <DonutSvg frac={0.25} colorA="var(--border-strong)" colorB="var(--bg-canvas)" hollow={type === "donut"} />;
  } else if (type === "line" || type === "area") {
    const real = realLinePoints(source, liveData);
    body = (
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" className={styles.chartSvg} aria-hidden="true">
        {real ? (
          <>
            {type === "area" && <polyline points={`0,40 ${polyline(real)} 100,40`} fill={a} opacity="0.25" stroke="none" />}
            <polyline points={polyline(real)} fill="none" stroke={a} strokeWidth="2" />
          </>
        ) : (
          <>
            {type === "area" && <path d="M0 34 L20 26 L40 20 L60 12 L80 8 L100 4 L100 40 L0 40 Z" fill={a} opacity="0.25" />}
            <polyline points="0,34 20,26 40,20 60,12 80,8 100,4" fill="none" stroke={a} strokeWidth="2" />
            <polyline points="0,36 20,32 40,28 60,22 80,18 100,14" fill="none" stroke={b} strokeWidth="2" strokeDasharray="4 3" />
          </>
        )}
      </svg>
    );
  } else {
    // bar / column / stacked all read as grouped bars at preview size.
    const real = realBarHeights(source, liveData, pinnedItem);
    const heights = real && real.length ? real : [60, 80, 45, 90, 70];
    body = (
      <div className={styles.barRow}>
        {heights.map((h, i) => (
          <div key={i} className={styles.barPair}>
            <span style={{ height: `${Math.max(4, h)}%`, background: a }} />
            {!real && <span style={{ height: `${Math.max(20, h - 20)}%`, background: b }} />}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={styles.chartPreview}>
      <div className={styles.chartBody}>{body}</div>
      <div className={styles.chartCaption}>{label(CHART_SOURCES, p.source, "Chart")}</div>
    </div>
  );
}

/** Reserves a header strip above and/or a footer strip under a table/chart
 * box — mirrors apps/reports/pdf_canvas.py's _TITLE_H/_CAPTION_H reservation
 * in _draw_table_element/_draw_chart_element. `titleShow` defaults to shown
 * (missing `show_title` counts as on — see _table_or_chart_title's
 * docstring on the backend); `captionShow` defaults to off, unchanged. The
 * caption's real PDF text is prefixed with a running "جدول N:"/"شكل N:"
 * number computed across the whole document (repeat expansion, table-
 * overflow pagination) — not reproducible from this one page in isolation,
 * so the canvas shows its name without a number rather than a wrong one;
 * the title carries no running number to begin with, so it matches exactly.
 * The *name* itself (both here and the title) now comes from the real
 * `labels` prop when the element has no title_text/caption of its own — see
 * PreviewProps.labels — so the only gap left versus the download is the
 * missing running number, not the language/wording. */
function CaptionedBox({
  titleShow, titleText, captionShow, captionText, children,
}: {
  titleShow: boolean; titleText: string; captionShow: boolean; captionText: string; children: React.ReactNode;
}) {
  if (!titleShow && !captionShow) return <>{children}</>;
  return (
    <div className={styles.captionedBox}>
      {titleShow && <div className={styles.elementTitle}>{titleText}</div>}
      <div className={styles.captionedBoxBody}>{children}</div>
      {captionShow && <div className={styles.elementCaption}>{captionText}</div>}
    </div>
  );
}

function TocPreview({ el, liveData, tocEntries, tocCaptions, ownPageId, onElementChange }: PreviewProps) {
  const p = el.props;
  const variant = String(p.variant ?? "contents");
  const size = Number(p.size ?? 11);
  const color = String(p.color ?? "#1e2430");
  // One global direction for the whole TOC — mirrors pdf_canvas.py's
  // _draw_toc_element exactly (`rtl = bool(ctx.get("arabic"))`, computed
  // once for the report, not re-guessed per row). A per-row guess would put
  // the page-number column on a different side for an Arabic row than an
  // English one, which the real PDF never does. Shared by all four variants
  // — the same report is either Arabic or not, regardless of which TOC list
  // is being shown.
  const rtl = liveData?.arabic ?? false;

  // "Tables"/"Figures"/"Images" variants list every OTHER captioned element
  // in the template, in final PDF page order — numbering that depends on
  // the whole document (repeat expansion, table-overflow pagination), not
  // just this one page's data, so it isn't something this per-page canvas
  // editor can recompute on its own the way the Contents variant does from
  // tocEntries. `tocCaptions` (see useTocEntries) is the real thing, fetched
  // from apps/reports/pdf_canvas.py's own _collect_captions pre-pass — the
  // same one the downloaded PDF runs — so this can't drift from it. Only
  // falls back to the old "resolved in the downloaded PDF" placeholder when
  // there's no real project data to ask at all (the Template Builder).
  if (variant !== "contents") {
    const label = variant === "tables" ? "tables" : variant === "figures" ? "figures / charts" : "images";
    if (!tocCaptions) {
      return (
        <div className={styles.chartPlaceholder}>
          {`List of ${label} — numbered and resolved in the downloaded PDF`}
        </div>
      );
    }
    const rows = tocCaptions[variant as "tables" | "figures" | "images"] ?? [];
    if (rows.length === 0) {
      return <div className={styles.chartPlaceholder}>{`No captioned ${label} yet`}</div>;
    }
    return (
      <div className={styles.tocPreview} dir={rtl ? "rtl" : "ltr"} style={{ fontSize: `${size}px`, color }}>
        {rows.map((row, i) => (
          <div key={i} className={styles.tocPreviewRow}>
            <span>{row.text}</span>
            <span className={styles.tocPreviewDots} />
            <span>{row.page}</span>
          </div>
        ))}
      </div>
    );
  }

  const excludeCover = p.exclude_cover ?? true;
  // A double-clicked row writes into props.name_overrides, keyed by page id
  // — the same keys pdf_canvas._draw_toc_element reads, so a renamed TOC
  // entry reaches the downloaded PDF too, without touching the page's own
  // title anywhere else.
  const nameOverrides = (p.name_overrides as Record<string, string> | undefined) ?? {};
  const commitName = onElementChange
    ? (pid: string, value: string) => {
        onElementChange({ ...el, props: { ...p, name_overrides: { ...nameOverrides, [pid]: value } } });
      }
    : undefined;

  // Real page names + real page numbers from the current draft — mirrors
  // apps/reports/pdf_canvas.py's _draw_toc_element exactly (same exclusion
  // rules, same "skip my own page" rule), never a fake sample list.
  const rows = (tocEntries ?? [])
    .filter((e) => e.id !== ownPageId)
    .filter((e) => !(excludeCover && e.name.trim().toLowerCase() === "cover"));

  if (!tocEntries) {
    return <div className={styles.chartPlaceholder}>Table of contents</div>;
  }

  return (
    <div className={styles.tocPreview} dir={rtl ? "rtl" : "ltr"} style={{ fontSize: `${size}px`, color }}>
      {rows.map((row) => (
        <div key={row.id} className={styles.tocPreviewRow}>
          <InlineEditableText
            value={nameOverrides[row.id] ?? row.name}
            onCommit={commitName && ((v) => commitName(row.id, v))}
          />
          <span className={styles.tocPreviewDots} />
          <span>{row.number}</span>
        </div>
      ))}
    </div>
  );
}

/** Real text for a field source, or null to fall back to the generic token. */
function resolveField(
  source: unknown, data: ReportData | null | undefined, pinnedItem: RepeatItem | RepeatItem[] | null | undefined,
  ownPageNumber?: number, ownPageTitle?: string,
): string | null {
  if (typeof source === "string" && source.startsWith("item.")) {
    return resolveItemField(source, singleItem(pinnedItem));
  }
  if (source === "page.number") return ownPageNumber != null ? String(ownPageNumber) : null;
  // Neither liveData nor pinnedItem — this page's own name is already known
  // purely from the page list (see ReportConfigurator's tocEntries), so a
  // divider heading resolves in the Template Builder too, not just a report.
  if (source === "page.title") return ownPageTitle || null;
  if (!data) return null;
  const p = data.project;
  switch (source) {
    case "project.name": return p.name || null;
    case "project.code": return p.code || null;
    case "project.client": return p.client || null;
    case "project.consultant": return p.consultant || null;
    case "project.contractor": return p.contractor || null;
    case "project.location": return p.location || null;
    case "project.description": return p.description || null;
    case "report.title": return data.report.title || null;
    case "report.number": return data.report.number || null;
    case "report.date": return fmtDate(data.report.date);
    case "report.period":
      return data.report.period_start && data.report.period_finish
        ? `${fmtDate(data.report.period_start)} – ${fmtDate(data.report.period_finish)}` : null;
    case "progress.overall": return fmtPct(data.overall);
    case "progress.planned": return data.planned != null ? fmtPct(data.planned) : null;
    default: return null;
  }
}

// "company"/"project" are the pre-relabel keys (see reportElements.ts's own
// note) — kept so a template saved before that fix still resolves sensibly.
const LOGO_SLOT: Record<string, "left" | "right" | "cover"> = {
  left: "left", right: "right", cover: "cover", company: "left", project: "right",
};

/** This logo element's real image URL, or null to fall back to the label. */
function resolveLogoUrl(props: Record<string, unknown>, data: ReportData | null | undefined): string | null {
  const source = String(props.source ?? "left");
  if (source === "upload") return (props.upload_url as string) || null;
  if (!data) return null;
  if (source === "extra") {
    const idx = Number(props.slot ?? 0);
    return data.logos.extra[idx]?.url || null;
  }
  const slot = LOGO_SLOT[source];
  return slot ? data.logos[slot]?.url || null : null;
}

/** An "image" element's real URL — either a "Photo slot" bound to one
 * photo/attachment in the current repeat chunk (props.slot indexes the
 * pinned group), or a specific image uploaded directly to this element
 * (props.upload_url, set by ElementInspector's upload control right after
 * upload — no extra round trip needed to preview it). Mirrors
 * apps/reports/pdf_canvas.py's _draw_image. */
function resolveImageUrl(props: Record<string, unknown>, pinnedItem: RepeatItem | RepeatItem[] | null | undefined): string | null {
  if (props.source === "upload") return (props.upload_url as string) || null;
  if (props.source !== "repeat.item" || !Array.isArray(pinnedItem)) return null;
  const slot = Number(props.slot ?? 0);
  const item = pinnedItem[slot];
  return (item?.url as string) || null;
}

/** This description element's own rich text (`props.html`, already-sanitized
 * HTML — see apps/reports/richtext.py's sanitize_html, the whitelisted-
 * tags-only output this is a direct render of, safe to drop straight into
 * the DOM) — a per-element block, edited directly in place here, the same
 * way any other canvas element's content is authored, rather than a
 * separate report-level field edited on its own tab. An inline table/chart/
 * image embed only resolves to real data in the downloaded PDF (see
 * richtext._resolve_embed) — there's no live-preview equivalent of that
 * resolution here, so an embed shows as a labeled placeholder chip instead
 * (driven by the `data-embed`/`data-spec` attributes the marker itself
 * already carries), same "honest placeholder over a wrong preview"
 * precedent as an unresolved TOC caption number elsewhere in this file.
 *
 * Double-click to edit in place: swaps in the real RichTextEditor (its own
 * toolbar plus the table/chart/image embed buttons) as a floating overlay
 * anchored to this box, large enough to comfortably work in regardless of
 * how small/zoomed-out the placed element is. A click outside commits the
 * draft into this element's own props and exits, the same "commit on
 * blur/outside-click, not on every keystroke" convention every other
 * inline-editable field on this canvas already uses (see
 * InlineEditableText) — editing a letter at a time would otherwise flood
 * undo history with one entry per keystroke. */
function DescriptionPreview({
  el, reportId, onElementChange,
}: {
  el: LayoutElement;
  reportId?: string;
  onElementChange?: (el: LayoutElement) => void;
}) {
  const html = typeof el.props.html === "string" ? el.props.html : "";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(html);
  const containerRef = useRef<HTMLDivElement>(null);
  const editorHandleRef = useRef<RichTextEditorHandle>(null);

  useEffect(() => { if (!editing) setDraft(html); }, [html, editing]);

  // The outside-click/Escape listener below binds once per edit session
  // (not per keystroke — see its own effect), so its handler closes over
  // whatever `draft`/`el`/`onElementChange` were at BIND time, not the
  // latest ones — refs keep it reading the current values on commit
  // instead of silently discarding everything typed since the edit began.
  const latest = useRef({ draft, html, el, onElementChange });
  useEffect(() => { latest.current = { draft, html, el, onElementChange }; });

  useEffect(() => {
    if (!editing) return;
    function commitAndExit() {
      setEditing(false);
      const { draft: d, html: h, el: e, onElementChange: change } = latest.current;
      if (d !== h) change?.({ ...e, props: { ...e.props, html: d } });
    }
    function onDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) commitAndExit();
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") commitAndExit();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [editing]);

  if (!onElementChange) {
    // Template Builder ghost / read-only — static render only, no editing.
    if (!html) return <div className={styles.chartPlaceholder}>Description</div>;
    return (
      <OverflowClip note="More content than fits here — continues in the downloaded PDF">
        {/* eslint-disable-next-line react/no-danger -- sanitize_html's whitelisted-tags-only output */}
        <div className={styles.descriptionPreview} dangerouslySetInnerHTML={{ __html: html }} />
      </OverflowClip>
    );
  }

  if (!editing) {
    return (
      <div
        className={styles.descriptionClickToEdit}
        onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
      >
        {html ? (
          <OverflowClip note="More content than fits here — continues in the downloaded PDF">
            {/* eslint-disable-next-line react/no-danger -- sanitize_html's whitelisted-tags-only output */}
            <div className={styles.descriptionPreview} dangerouslySetInnerHTML={{ __html: html }} />
          </OverflowClip>
        ) : (
          <div className={styles.chartPlaceholder}>Double-click to write the description</div>
        )}
      </div>
    );
  }

  return (
    <div ref={containerRef} className={styles.descriptionEditOverlay} onPointerDown={(e) => e.stopPropagation()}>
      <RichTextEditor
        ref={editorHandleRef}
        value={draft}
        onChange={setDraft}
        placeholder="Write the report's description — نسّق النص كما تريد…"
        extraToolbar={
          <DescriptionEmbedToolbar
            reportId={reportId}
            onInsert={(chip) => editorHandleRef.current?.insertHtml(chip)}
          />
        }
      />
    </div>
  );
}

export function ElementPreview({
  el, scale, liveData, reportId, pinnedItem, chartSvgs, tableData, tocCaptions, previewsReady, labels, tocEntries,
  ownPageId, onElementChange,
}: PreviewProps) {
  const p = el.props;

  switch (el.type) {
    case "text":
      return (
        <div
          className={styles.textPreview}
          style={{
            fontSize: `${ptToPx(Number(p.size ?? 11), scale)}px`,
            color: String(p.color ?? "#1e2430"),
            textAlign: (p.align as "left" | "center" | "right") ?? "left",
            fontWeight: p.bold ? 700 : 400,
            fontStyle: p.italic ? "italic" : "normal",
          }}
        >
          <InlineEditableText
            value={String(p.text ?? "Text")}
            onCommit={onElementChange && ((v) => onElementChange({ ...el, props: { ...p, text: v } }))}
          />
        </div>
      );

    case "field": {
      const ownPage = tocEntries?.find((e) => e.id === ownPageId);
      // A manual override (see pdf_canvas._draw_field's docstring) replaces
      // the live-computed value outright — real PDF and preview both check
      // it before falling back to resolveField.
      const override = p.value_override as string | undefined;
      const real = override ?? resolveField(p.source, liveData, pinnedItem, ownPage?.number, ownPage?.name);
      const commitValue = onElementChange
        ? (v: string) => onElementChange({ ...el, props: { ...p, value_override: v } })
        : undefined;
      return (
        <div
          className={styles.fieldPreview}
          style={{
            fontSize: `${ptToPx(Number(p.size ?? 11), scale)}px`,
            color: String(p.color ?? "#1e2430"),
            textAlign: (p.align as "left" | "center" | "right") ?? "left",
            fontWeight: p.bold ? 700 : 400,
          }}
        >
          {p.show_label && p.label ? `${String(p.label)} ` : ""}
          {real != null
            ? <InlineEditableText value={real} onCommit={commitValue} />
            : <span className={styles.fieldToken}>{label(FIELD_SOURCES, p.source, "Field")}</span>}
        </div>
      );
    }

    case "image": {
      const url = resolveImageUrl(p, pinnedItem);
      return url ? (
        // eslint-disable-next-line @next/next/no-img-element -- authed streaming URL, not an optimizable public asset
        <img
          className={styles.imagePreviewReal} src={url} alt=""
          style={{ ...imageFitStyle(p), ...imageBorderStyle(p) }}
        />
      ) : (
        <div className={styles.imagePreview}>
          <span>Image</span>
        </div>
      );
    }

    case "logo": {
      const url = resolveLogoUrl(p, liveData);
      return url ? (
        // eslint-disable-next-line @next/next/no-img-element -- authed streaming URL, not an optimizable public asset
        <img className={styles.imagePreviewReal} src={url} alt="" style={imageBorderStyle(p)} />
      ) : (
        <div className={styles.logoPreview}>
          <span>{p.source === "project" ? "Project logo" : "Company logo"}</span>
        </div>
      );
    }

    case "rect":
      return (
        <div
          className={styles.shapePreview}
          style={{
            background: String(p.fill ?? "#eef3f8"),
            border: `${Number(p.stroke_width ?? 0.5)}mm solid ${String(p.stroke ?? "#1F4E79")}`,
            borderRadius: `${Number(p.radius ?? 0)}mm`,
          }}
        />
      );

    case "ellipse":
      return (
        <div
          className={styles.shapePreview}
          style={{
            background: String(p.fill ?? "#eef3f8"),
            border: `${Number(p.stroke_width ?? 0.5)}mm solid ${String(p.stroke ?? "#1F4E79")}`,
            borderRadius: "50%",
          }}
        />
      );

    case "line":
      return (
        <div className={styles.linePreviewWrap}>
          <div
            className={styles.linePreview}
            style={{
              borderTop: `${Number(p.stroke_width ?? 0.6)}mm solid ${String(p.stroke ?? "#1F4E79")}`,
            }}
          />
        </div>
      );

    case "table":
      return (
        <CaptionedBox
          titleShow={p.show_title !== false}
          titleText={String(p.title_text || sourceLabel(labels, TABLE_SOURCES, p.source, "Table"))}
          captionShow={Boolean(p.show_caption)}
          captionText={String(p.caption || sourceLabel(labels, TABLE_SOURCES, p.source, "Table"))}
        >
          <TablePreview
            el={el} scale={scale} liveData={liveData} pinnedItem={pinnedItem}
            tableData={tableData} previewsReady={previewsReady} labels={labels}
            onElementChange={onElementChange}
          />
        </CaptionedBox>
      );

    case "chart":
      return (
        <CaptionedBox
          titleShow={p.show_title !== false}
          titleText={String(p.title_text || sourceLabel(labels, CHART_SOURCES, p.source, "Chart"))}
          captionShow={Boolean(p.show_caption)}
          captionText={String(p.caption || sourceLabel(labels, CHART_SOURCES, p.source, "Chart"))}
        >
          <ChartPreview
            el={el} scale={scale} liveData={liveData} pinnedItem={pinnedItem}
            chartSvgs={chartSvgs} previewsReady={previewsReady} labels={labels}
          />
        </CaptionedBox>
      );

    case "toc":
      return (
        <TocPreview
          el={el} scale={scale} liveData={liveData} tocEntries={tocEntries} tocCaptions={tocCaptions}
          ownPageId={ownPageId} onElementChange={onElementChange}
        />
      );

    case "description":
      return <DescriptionPreview el={el} reportId={reportId} onElementChange={onElementChange} />;

    default:
      return null;
  }
}
