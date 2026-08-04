"use client";

// Right panel: exact position/size plus the selected element's own settings.
// Field lists are declarative per element type so adding a knob is one line.
import {
  CHART_SOURCES, CHART_TYPES, FIELD_SOURCES, ITEM_CHART_SOURCES, ITEM_FIELD_SOURCES,
  ITEM_TABLE_SOURCES, TABLE_SOURCES,
} from "@/lib/reportElements";
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

/** Image source: a fixed logo/cover slot, or a repeat-page photo slot (only
 * meaningful once the active page is marked "repeat" — see `repeating`). */
const IMAGE_SOURCES = [
  { value: "left", label: "Left logo" },
  { value: "right", label: "Right logo" },
  { value: "cover", label: "Cover image" },
  { value: "repeat.item", label: "Repeat photo slot" },
];

/** Logo element source — left/right/cover are the fixed single slots;
 * "extra" picks one of any number of additional uploaded logos by index. */
const LOGO_SOURCES = [
  { value: "left", label: "Left logo" },
  { value: "right", label: "Right logo" },
  { value: "cover", label: "Cover image" },
  { value: "extra", label: "Additional logo (pick slot below)" },
];

/** Field lists per element type. `repeating` appends the item-scoped sources
 * (only resolvable on a page that clones itself per photo/zone/etc). */
function typeFields(type: string, repeating: boolean): PropField[] {
  switch (type) {
    case "text":
      return [
        { path: "text", label: "Text", kind: "text" },
        { path: "size", label: "Size (pt)", kind: "number" },
        { path: "color", label: "Color", kind: "color" },
        { path: "align", label: "Align", kind: "select", options: ALIGN },
        { path: "bold", label: "Bold", kind: "toggle" },
        { path: "italic", label: "Italic", kind: "toggle" },
      ];
    case "field":
      return [
        { path: "source", label: "Value", kind: "select",
          options: repeating ? [...FIELD_SOURCES, ...ITEM_FIELD_SOURCES] : FIELD_SOURCES },
        { path: "label", label: "Prefix label", kind: "text" },
        { path: "show_label", label: "Show prefix", kind: "toggle" },
        { path: "size", label: "Size (pt)", kind: "number" },
        { path: "color", label: "Color", kind: "color" },
        { path: "align", label: "Align", kind: "select", options: ALIGN },
        { path: "bold", label: "Bold", kind: "toggle" },
      ];
    case "image":
      return [
        { path: "source", label: "Image", kind: "select", options: IMAGE_SOURCES },
        { path: "slot", label: "Repeat slot (0, 1, 2…)", kind: "number" },
        { path: "show_caption", label: "Show caption", kind: "toggle" },
        { path: "fit", label: "Fit", kind: "select", options: [
          { value: "cover", label: "Cover" }, { value: "contain", label: "Contain" }] },
      ];
    case "logo":
      return [
        { path: "source", label: "Image", kind: "select", options: LOGO_SOURCES },
        { path: "slot", label: "Additional-logo slot (0, 1, 2…)", kind: "number" },
      ];
    case "rect":
      return [
        { path: "fill", label: "Fill", kind: "color" },
        { path: "stroke", label: "Border", kind: "color" },
        { path: "stroke_width", label: "Border width (mm)", kind: "number", step: 0.1 },
        { path: "radius", label: "Corner radius (mm)", kind: "number", step: 0.5 },
      ];
    case "ellipse":
      return [
        { path: "fill", label: "Fill", kind: "color" },
        { path: "stroke", label: "Border", kind: "color" },
        { path: "stroke_width", label: "Border width (mm)", kind: "number", step: 0.1 },
      ];
    case "line":
      return [
        { path: "stroke", label: "Color", kind: "color" },
        { path: "stroke_width", label: "Thickness (mm)", kind: "number", step: 0.1 },
      ];
    case "table":
      return [
        { path: "source", label: "Data", kind: "select",
          options: repeating ? [...TABLE_SOURCES, ...ITEM_TABLE_SOURCES] : TABLE_SOURCES },
        { path: "zebra", label: "Zebra rows", kind: "toggle" },
        { path: "border", label: "Borders", kind: "toggle" },
        { path: "header_bg", label: "Header fill", kind: "color" },
        { path: "header_text", label: "Header text", kind: "color" },
      ];
    case "chart":
      return [
        { path: "source", label: "Data", kind: "select",
          options: repeating ? [...CHART_SOURCES, ...ITEM_CHART_SOURCES] : CHART_SOURCES },
        { path: "chart_type", label: "Chart type", kind: "select", options: CHART_TYPES },
        { path: "legend", label: "Show legend", kind: "toggle" },
        { path: "color_a", label: "Series A", kind: "color" },
        { path: "color_b", label: "Series B", kind: "color" },
      ];
    case "toc":
      return [
        { path: "size", label: "Size (pt)", kind: "number" },
        { path: "row_height", label: "Row height (mm)", kind: "number", step: 0.5 },
        { path: "color", label: "Color", kind: "color" },
        { path: "exclude_cover", label: "Exclude cover page", kind: "toggle" },
      ];
    default:
      return [];
  }
}

interface Props {
  el: LayoutElement | null;
  onChange: (el: LayoutElement) => void;
  /** True when the active page (or master) is set to repeat — unlocks the
   * item-scoped source options above. */
  repeating?: boolean;
}

export function ElementInspector({ el, onChange, repeating = false }: Props) {
  if (!el) {
    return (
      <aside className={styles.inspector} aria-label="Element properties">
        <h2 className={styles.panelTitle}>Properties</h2>
        <p className={styles.panelHint}>Select an element on the page to edit it.</p>
      </aside>
    );
  }

  const fields = typeFields(el.type, repeating);

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
