"use client";

// Right panel: exact position/size plus the selected element's own settings.
// Field lists are declarative per element type so adding a knob is one line.
import { CHART_SOURCES, CHART_TYPES, FIELD_SOURCES, TABLE_SOURCES } from "@/lib/reportElements";
import type { LayoutElement } from "@/lib/reportLayout";
import styles from "./designer.module.css";

type PropField =
  | { path: string; label: string; kind: "text" }
  | { path: string; label: string; kind: "number"; step?: number }
  | { path: string; label: string; kind: "color" }
  | { path: string; label: string; kind: "toggle" }
  | { path: string; label: string; kind: "select"; options: { value: string; label: string }[] };

const ALIGN = [
  { value: "left", label: "Left" },
  { value: "center", label: "Center" },
  { value: "right", label: "Right" },
];

const TYPE_FIELDS: Record<string, PropField[]> = {
  text: [
    { path: "text", label: "Text", kind: "text" },
    { path: "size", label: "Size (pt)", kind: "number" },
    { path: "color", label: "Color", kind: "color" },
    { path: "align", label: "Align", kind: "select", options: ALIGN },
    { path: "bold", label: "Bold", kind: "toggle" },
    { path: "italic", label: "Italic", kind: "toggle" },
  ],
  field: [
    { path: "source", label: "Value", kind: "select", options: FIELD_SOURCES },
    { path: "label", label: "Prefix label", kind: "text" },
    { path: "show_label", label: "Show prefix", kind: "toggle" },
    { path: "size", label: "Size (pt)", kind: "number" },
    { path: "color", label: "Color", kind: "color" },
    { path: "align", label: "Align", kind: "select", options: ALIGN },
    { path: "bold", label: "Bold", kind: "toggle" },
  ],
  image: [
    { path: "fit", label: "Fit", kind: "select", options: [
      { value: "cover", label: "Cover" }, { value: "contain", label: "Contain" }] },
  ],
  logo: [
    { path: "source", label: "Logo", kind: "select", options: [
      { value: "company", label: "Company" }, { value: "project", label: "Project" }] },
  ],
  rect: [
    { path: "fill", label: "Fill", kind: "color" },
    { path: "stroke", label: "Border", kind: "color" },
    { path: "stroke_width", label: "Border width (mm)", kind: "number", step: 0.1 },
    { path: "radius", label: "Corner radius (mm)", kind: "number", step: 0.5 },
  ],
  ellipse: [
    { path: "fill", label: "Fill", kind: "color" },
    { path: "stroke", label: "Border", kind: "color" },
    { path: "stroke_width", label: "Border width (mm)", kind: "number", step: 0.1 },
  ],
  line: [
    { path: "stroke", label: "Color", kind: "color" },
    { path: "stroke_width", label: "Thickness (mm)", kind: "number", step: 0.1 },
  ],
  table: [
    { path: "source", label: "Data", kind: "select", options: TABLE_SOURCES },
    { path: "zebra", label: "Zebra rows", kind: "toggle" },
    { path: "border", label: "Borders", kind: "toggle" },
    { path: "header_bg", label: "Header fill", kind: "color" },
    { path: "header_text", label: "Header text", kind: "color" },
  ],
  chart: [
    { path: "source", label: "Data", kind: "select", options: CHART_SOURCES },
    { path: "chart_type", label: "Chart type", kind: "select", options: CHART_TYPES },
    { path: "legend", label: "Show legend", kind: "toggle" },
    { path: "color_a", label: "Series A", kind: "color" },
    { path: "color_b", label: "Series B", kind: "color" },
  ],
};

interface Props {
  el: LayoutElement | null;
  onChange: (el: LayoutElement) => void;
}

export function ElementInspector({ el, onChange }: Props) {
  if (!el) {
    return (
      <aside className={styles.inspector} aria-label="Element properties">
        <h2 className={styles.panelTitle}>Properties</h2>
        <p className={styles.panelHint}>Select an element on the page to edit it.</p>
      </aside>
    );
  }

  const fields = TYPE_FIELDS[el.type] ?? [];

  function setProp(path: string, value: unknown) {
    onChange({ ...el!, props: { ...el!.props, [path]: value } });
  }

  function setGeom(key: "x" | "y" | "w" | "h", value: number) {
    onChange({ ...el!, [key]: value });
  }

  return (
    <aside className={styles.inspector} aria-label="Element properties">
      <h2 className={styles.panelTitle}>{el.type} properties</h2>

      <div className={styles.geomGrid}>
        {(["x", "y", "w", "h"] as const).map((k) => (
          <label key={k} className={styles.geomField}>
            <span>{k.toUpperCase()} (mm)</span>
            <input
              type="number"
              step={1}
              value={el[k]}
              onChange={(e) => setGeom(k, Number(e.target.value))}
            />
          </label>
        ))}
      </div>

      <div className={styles.propFields}>
        {fields.map((f) => {
          const value = el.props[f.path];
          if (f.kind === "toggle") {
            return (
              <label key={f.path} className={styles.propToggle}>
                <input
                  type="checkbox"
                  checked={Boolean(value)}
                  onChange={(e) => setProp(f.path, e.target.checked)}
                />
                <span>{f.label}</span>
              </label>
            );
          }
          return (
            <label key={f.path} className={styles.propField}>
              <span>{f.label}</span>
              {f.kind === "select" ? (
                <select value={String(value ?? "")} onChange={(e) => setProp(f.path, e.target.value)}>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              ) : f.kind === "color" ? (
                <input
                  type="color"
                  value={String(value ?? "#000000")}
                  onChange={(e) => setProp(f.path, e.target.value)}
                />
              ) : f.kind === "number" ? (
                <input
                  type="number"
                  step={f.step ?? 1}
                  value={Number(value ?? 0)}
                  onChange={(e) => setProp(f.path, Number(e.target.value))}
                />
              ) : (
                <input
                  type="text"
                  value={String(value ?? "")}
                  onChange={(e) => setProp(f.path, e.target.value)}
                />
              )}
            </label>
          );
        })}
      </div>
    </aside>
  );
}
