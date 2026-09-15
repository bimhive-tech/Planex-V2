"use client";

// The "Chart style" block of the Properties panel: one chart element's own
// colours and wording. Every prop written here is read by the backend
// (pdf_charts.chart_style_override), so a change is what the downloaded PDF
// draws — never a canvas-only tint. Text size and the legend/values toggles
// sit with the element's other fields; this block holds what needs the
// report's own defaults to make sense: a picker that opened on black, or a
// blank box where the legend entry's real text should be, told the user
// nothing about what they were replacing.
import { Button } from "@/components/ui/Button";
import { DraftInput } from "@/components/ui/DraftInput";
import { CHART_COLOR_PROPS, CHART_STYLE_PROPS, CHART_TEXT_KEYS } from "@/lib/reportElements";
import type { LayoutElement, ReportColors, ReportLabels } from "@/lib/reportLayout";
import styles from "./designer.module.css";

interface Props {
  el: LayoutElement;
  /** The report's effective labels/colours — the defaults each control
   * shows until this element overrides it. Undefined in the Template
   * Builder, where the block still edits but shows no defaults. */
  labels?: ReportLabels;
  chartColors?: ReportColors;
  /** What each palette colour paints, when the chart's data names it (a
   * submittal chart's disciplines): those names label the pickers. */
  series?: string[];
  onChange: (el: LayoutElement) => void;
}

/** The report's own colour behind a picker this element hasn't set. */
function defaultColor(colors: ReportColors | undefined, colorKey: string, paletteIndex?: number): string {
  const value = colors?.[colorKey];
  if (paletteIndex != null) {
    return (Array.isArray(value) && value[paletteIndex]) || "#000000";
  }
  return typeof value === "string" ? value : "#000000";
}

export function ChartStyleBlock({ el, labels, chartColors, series, onChange }: Props) {
  const p = el.props;
  const textKeys = CHART_TEXT_KEYS[String(p.source ?? "")] ?? [];
  const texts = (p.text_labels as Record<string, string> | undefined) ?? {};
  const styled = CHART_STYLE_PROPS.some((k) => p[k] !== undefined);

  function setProp(path: string, value: unknown) {
    onChange({ ...el, props: { ...p, [path]: value } });
  }

  function setText(key: string, value: string) {
    // An emptied box goes back to the report's own wording rather than
    // printing nothing.
    const next = { ...texts };
    if (value.trim()) next[key] = value; else delete next[key];
    setProp("text_labels", Object.keys(next).length ? next : undefined);
  }

  function reset() {
    const props = { ...p };
    for (const key of CHART_STYLE_PROPS) delete props[key];
    onChange({ ...el, props });
  }

  return (
    <div className={styles.uploadBlock}>
      <h3 className={styles.styleHeading}>Chart style</h3>
      <p className={styles.panelHint}>
        Colours and wording for this one chart. Pickers start on the report&apos;s own colours; an
        emptied text goes back to the report&apos;s wording.
      </p>
      <div className={styles.styleColorGrid}>
        {CHART_COLOR_PROPS.map((c) => (
          <label key={c.path} className={styles.propField}>
            <span>{(c.paletteIndex != null && series?.[c.paletteIndex]) || c.label}</span>
            <input
              type="color"
              value={String(p[c.path] ?? defaultColor(chartColors, c.colorKey, c.paletteIndex))}
              onChange={(e) => setProp(c.path, e.target.value)}
            />
          </label>
        ))}
      </div>
      {textKeys.length > 0 && (
        <div className={styles.propFields}>
          {textKeys.map((key) => (
            <label key={key} className={styles.propField}>
              <span>{labels?.[key] ?? key}</span>
              <DraftInput
                type="text"
                value={texts[key] ?? ""}
                placeholder={labels?.[key] ?? key}
                onCommit={(v) => setText(key, v)}
              />
            </label>
          ))}
        </div>
      )}
      {styled && (
        <Button type="button" variant="secondary" size="sm" onClick={reset}>
          Reset chart style
        </Button>
      )}
    </div>
  );
}
