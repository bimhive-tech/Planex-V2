"use client";

// How each element type looks on the canvas. When liveData is available (the
// report-level "Customize" tab — see ReportLayoutEditor), tables/charts/
// fields/images show this project's actual content instead of generic
// placeholders, so editing looks like editing the real thing. pinnedItem is
// the specific zone/photo/etc. an expanded repeating page was pinned to (see
// reportRepeat.ts), letting item.* bindings resolve too. In the project-
// agnostic Template Builder both are undefined and every element falls back
// to the representative placeholder it always showed.
import { CHART_SOURCES, FIELD_SOURCES, TABLE_SOURCES } from "@/lib/reportElements";
import type { LayoutElement } from "@/lib/reportLayout";
import { resolveItemField } from "@/lib/reportRepeat";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
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
  pinnedItem?: RepeatItem | RepeatItem[] | null;
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

/** item.* sources bind to one item, never a chunk group. */
function singleItem(pinnedItem: RepeatItem | RepeatItem[] | null | undefined): RepeatItem | null {
  if (!pinnedItem) return null;
  return Array.isArray(pinnedItem) ? (pinnedItem[0] ?? null) : pinnedItem;
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
    ["Location", p.location], ["Value", money(p.budget, p.currency)],
    ["Contract value", money(p.contract_value, p.currency)],
    ["Approved value", money(p.approved_value, p.currency)],
    ["Forecast cost", money(p.forecast_cost, p.currency)],
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

function TablePreview({ el, liveData, pinnedItem }: PreviewProps) {
  const p = el.props;
  const headerBg = String(p.header_bg ?? "#1F4E79");
  const headerText = String(p.header_text ?? "#ffffff");
  const real = realTableRows(p.source, liveData, pinnedItem);
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

function ChartPreview({ el, liveData, pinnedItem }: PreviewProps) {
  const p = el.props;
  const type = String(p.chart_type ?? "column");
  const source = p.source;
  const a = String(p.color_a ?? "#4F81BD");
  const b = String(p.color_b ?? "#C0504D");
  const item = singleItem(pinnedItem);

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

function TocPreview() {
  return (
    <div className={styles.tocPreview}>
      {["Cover", "Project Info", "Executive Dashboard", "Cash Flow", "Photos"].map((name, i) => (
        <div key={name} className={styles.tocPreviewRow}>
          <span>{name}</span>
          <span className={styles.tocPreviewDots} />
          <span>{i + 1}</span>
        </div>
      ))}
    </div>
  );
}

/** Real text for a field source, or null to fall back to the generic token. */
function resolveField(source: unknown, data: ReportData | null | undefined, pinnedItem: RepeatItem | RepeatItem[] | null | undefined): string | null {
  if (typeof source === "string" && source.startsWith("item.")) {
    return resolveItemField(source, singleItem(pinnedItem));
  }
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
    default: return null; // page.number is resolved at PDF-render time only
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

export function ElementPreview({ el, scale, liveData, pinnedItem }: PreviewProps) {
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
          {String(p.text ?? "Text")}
        </div>
      );

    case "field": {
      const real = resolveField(p.source, liveData, pinnedItem);
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
          {real ?? <span className={styles.fieldToken}>{label(FIELD_SOURCES, p.source, "Field")}</span>}
        </div>
      );
    }

    case "image": {
      const url = resolveImageUrl(p, pinnedItem);
      return url ? (
        // eslint-disable-next-line @next/next/no-img-element -- authed streaming URL, not an optimizable public asset
        <img className={styles.imagePreviewReal} src={url} alt="" />
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
        <img className={styles.imagePreviewReal} src={url} alt="" />
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
      return <TablePreview el={el} scale={scale} liveData={liveData} pinnedItem={pinnedItem} />;

    case "chart":
      return <ChartPreview el={el} scale={scale} liveData={liveData} pinnedItem={pinnedItem} />;

    case "toc":
      return <TocPreview />;

    default:
      return null;
  }
}
