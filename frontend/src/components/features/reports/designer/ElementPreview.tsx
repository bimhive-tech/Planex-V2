"use client";

// How each element type looks on the canvas. Tables and charts show a
// representative preview (not live project data) — the real values are bound
// when the report renders, so the designer stays fast and project-agnostic.
import { CHART_SOURCES, FIELD_SOURCES, TABLE_SOURCES } from "@/lib/reportElements";
import type { LayoutElement } from "@/lib/reportLayout";
import styles from "./designer.module.css";

function label(list: { value: string; label: string }[], value: unknown, fallback: string) {
  return list.find((o) => o.value === value)?.label ?? fallback;
}

function TablePreview({ el }: { el: LayoutElement }) {
  const p = el.props;
  const headerBg = String(p.header_bg ?? "#1F4E79");
  const headerText = String(p.header_text ?? "#ffffff");
  return (
    <div className={styles.tablePreview}>
      <div className={styles.tablePreviewHead} style={{ background: headerBg, color: headerText }}>
        {label(TABLE_SOURCES, p.source, "Table")}
      </div>
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className={styles.tablePreviewRow}
          data-zebra={p.zebra && i % 2 === 1 ? "on" : undefined}
        >
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

function ChartPreview({ el }: { el: LayoutElement }) {
  const p = el.props;
  const type = String(p.chart_type ?? "column");
  const a = String(p.color_a ?? "#2E74B5");
  const b = String(p.color_b ?? "#C0504D");

  let body: React.ReactNode;
  if (type === "pie" || type === "donut") {
    body = (
      <svg viewBox="0 0 36 36" className={styles.chartSvg} aria-hidden="true">
        <circle cx="18" cy="18" r="16" fill={b} />
        <path d="M18 2 A16 16 0 0 1 34 18 L18 18 Z" fill={a} />
        {type === "donut" && <circle cx="18" cy="18" r="8" fill="#fff" />}
      </svg>
    );
  } else if (type === "line" || type === "area") {
    body = (
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" className={styles.chartSvg} aria-hidden="true">
        {type === "area" && <path d="M0 34 L20 26 L40 20 L60 12 L80 8 L100 4 L100 40 L0 40 Z" fill={a} opacity="0.25" />}
        <polyline points="0,34 20,26 40,20 60,12 80,8 100,4" fill="none" stroke={a} strokeWidth="2" />
        <polyline points="0,36 20,32 40,28 60,22 80,18 100,14" fill="none" stroke={b} strokeWidth="2" strokeDasharray="4 3" />
      </svg>
    );
  } else {
    // bar / column / stacked all read as grouped bars at preview size.
    const heights = [60, 80, 45, 90, 70];
    body = (
      <div className={styles.barRow}>
        {heights.map((h, i) => (
          <div key={i} className={styles.barPair}>
            <span style={{ height: `${h}%`, background: a }} />
            <span style={{ height: `${Math.max(20, h - 20)}%`, background: b }} />
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

export function ElementPreview({ el }: { el: LayoutElement }) {
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

    case "field":
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
          <span className={styles.fieldToken}>{label(FIELD_SOURCES, p.source, "Field")}</span>
        </div>
      );

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
      return <TablePreview el={el} />;

    case "chart":
      return <ChartPreview el={el} />;

    case "toc":
      return <TocPreview />;

    default:
      return null;
  }
}
