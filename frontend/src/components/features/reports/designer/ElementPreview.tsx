"use client";

// How each element type looks on the canvas. When liveData is available (the
// report-level "Customize" tab — see ReportLayoutEditor), tables/charts/fields
// show this project's actual numbers instead of generic placeholder content,
// so editing looks like editing the real thing. In the project-agnostic
// Template Builder liveData is undefined and every element falls back to the
// representative placeholder it always showed.
import { CHART_SOURCES, FIELD_SOURCES, TABLE_SOURCES } from "@/lib/reportElements";
import type { LayoutElement } from "@/lib/reportLayout";
import type { ReportData } from "@/types/report";
import styles from "./designer.module.css";

function label(list: { value: string; label: string }[], value: unknown, fallback: string) {
  return list.find((o) => o.value === value)?.label ?? fallback;
}

const fmtDate = (d: string | null) => (d ? new Date(d).toLocaleDateString(undefined, { day: "2-digit", month: "short" }) : "—");
const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(0)}%`);

/** Real row cells for a table source, or null when there's no live data (or
 * nothing to show) for it — the caller falls back to placeholder bars. */
function realTableRows(source: unknown, data: ReportData | null | undefined): string[][] | null {
  if (!data) return null;
  switch (source) {
    case "project_info": {
      const p = data.project;
      const rows: [string, string][] = [
        ["Name", p.name], ["Client", p.client], ["Location", p.location],
        ["Value", p.budget ? `${Number(p.budget).toLocaleString()} ${p.currency}` : ""],
      ];
      const filtered = rows.filter(([, v]) => v);
      return filtered.length ? filtered.slice(0, 4) : null;
    }
    case "zone_progress":
      return data.zones.length ? data.zones.slice(0, 4).map((z) => [z.name, fmtPct(z.progress)]) : null;
    case "hierarchy_progress":
      return data.hierarchy.length
        ? data.hierarchy.slice(0, 4).map((h) => [h.name, fmtPct(h.actual)]) : null;
    case "discipline_progress":
      return data.discipline.length
        ? data.discipline.slice(0, 4).map((d) => [d.name, fmtPct(d.concrete)]) : null;
    case "progress_compare": {
      const rows = data.zones.filter((z) => z.planned != null);
      return rows.length ? rows.slice(0, 4).map((z) => [z.name, fmtPct(z.planned), fmtPct(z.progress)]) : null;
    }
    case "critical_path_delays":
      return data.critical_path.length
        ? data.critical_path.slice(0, 4).map((r) => [r.name, `${r.delay_days}d`]) : null;
    case "milestones":
      return data.milestones.length
        ? data.milestones.slice(0, 4).map((m) => [m.title, fmtDate(m.date)]) : null;
    case "invoices":
      return data.invoices.length
        ? data.invoices.slice(0, 4).map((i) => [i.name, i.value.toLocaleString()]) : null;
    case "submittals":
      return data.submittals.rows.length
        ? data.submittals.rows.slice(0, 4).map((s) => [s.title, s.status]) : null;
    case "delays":
      return data.delays.length
        ? data.delays.slice(0, 4).map((d) => [d.title, `${d.impact_days}d`]) : null;
    default:
      return null; // detailed_progress — the real grid is heavy and not sent to the builder
  }
}

function TablePreview({ el, liveData }: { el: LayoutElement; liveData?: ReportData | null }) {
  const p = el.props;
  const headerBg = String(p.header_bg ?? "#1F4E79");
  const headerText = String(p.header_text ?? "#ffffff");
  const real = realTableRows(p.source, liveData);
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
function realBarHeights(source: unknown, data: ReportData | null | undefined): number[] | null {
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

function GaugeSvg({ value, color, track }: { value: number; color: string; track: string }) {
  const pct = Math.max(0, Math.min(100, value));
  const angle = -90 + (pct / 100) * 180;
  const needle = [18 + 13 * Math.cos((angle * Math.PI) / 180), 18 + 13 * Math.sin((angle * Math.PI) / 180)];
  return (
    <svg viewBox="0 0 36 22" className={styles.chartSvg} aria-hidden="true">
      <path d="M2 18 A16 16 0 0 1 34 18" fill="none" stroke={track} strokeWidth="4" strokeLinecap="round" />
      <path
        d="M2 18 A16 16 0 0 1 34 18" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round"
        strokeDasharray={`${(pct / 100) * 50.2} 50.2`}
      />
      <line x1="18" y1="18" x2={needle[0]} y2={needle[1]} stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="18" cy="18" r="1.5" fill={color} />
      <text x="18" y="21.5" fontSize="4" textAnchor="middle" fill={color}>{pct.toFixed(0)}%</text>
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

function ChartPreview({ el, liveData }: { el: LayoutElement; liveData?: ReportData | null }) {
  const p = el.props;
  const type = String(p.chart_type ?? "column");
  const source = p.source;
  const a = String(p.color_a ?? "#2E74B5");
  const b = String(p.color_b ?? "#C0504D");

  let body: React.ReactNode;
  if (type === "gauge") {
    const value = source === "spi" && liveData ? liveData.overall : 65;
    body = <GaugeSvg value={value} color={a} track={b} />;
  } else if (type === "pie" || type === "donut") {
    const frac = source === "breakdown" && liveData?.breakdown.total
      ? liveData.breakdown.completed / liveData.breakdown.total
      : source === "duration" && liveData?.duration?.total
        ? liveData.duration.elapsed / liveData.duration.total
        : 0.25;
    body = <DonutSvg frac={frac} colorA={a} colorB={b} hollow={type === "donut"} />;
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
    const real = realBarHeights(source, liveData);
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
function resolveField(source: unknown, data: ReportData | null | undefined): string | null {
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

export function ElementPreview({ el, liveData }: { el: LayoutElement; liveData?: ReportData | null }) {
  const p = el.props;

  switch (el.type) {
    case "text":
      return (
        <div
          className={styles.textPreview}
          style={{
            fontSize: `${Number(p.size ?? 11)}pt`,
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
      const real = resolveField(p.source, liveData);
      return (
        <div
          className={styles.fieldPreview}
          style={{
            fontSize: `${Number(p.size ?? 11)}pt`,
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

    case "image":
      return (
        <div className={styles.imagePreview}>
          <span>Image</span>
        </div>
      );

    case "logo":
      return (
        <div className={styles.logoPreview}>
          <span>{p.source === "project" ? "Project logo" : "Company logo"}</span>
        </div>
      );

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
      return <TablePreview el={el} liveData={liveData} />;

    case "chart":
      return <ChartPreview el={el} liveData={liveData} />;

    case "toc":
      return <TocPreview />;

    default:
      return null;
  }
}
