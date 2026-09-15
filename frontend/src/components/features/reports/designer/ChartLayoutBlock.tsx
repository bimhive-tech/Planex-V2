"use client";

// The "Axes, bars and legend" block of the Properties panel (register D2): a
// chart element's value axis range, bar and line sizing, legend position,
// decimals and — on a gauge — its bands. Every prop is read by the backend
// (pdf_charts.chart_options / chart_style_override), so the canvas preview
// and the downloaded PDF change together. A blank number means "as the chart
// is designed", so clearing a box undoes it.
import { DraftInput } from "@/components/ui/DraftInput";
import {
  CHART_AXIS_PROPS, CHART_DECIMALS, CHART_LEGEND_POSITIONS, GAUGE_COLOR_PROPS, GAUGE_NUMBER_PROPS,
  isGaugeChart,
} from "@/lib/reportElements";
import type { ChartNumberProp } from "@/lib/reportElements";
import type { LayoutElement, ReportColors } from "@/lib/reportLayout";
import styles from "./designer.module.css";

interface Props {
  el: LayoutElement;
  /** The report's own colours, shown by a band picker this element hasn't set. */
  chartColors?: ReportColors;
  onChange: (el: LayoutElement) => void;
}

/** A blank box (unset) or a real number — anything half-typed is refused. */
const blankOrNumber = (v: string) => v.trim() === "" || Number.isFinite(Number(v));

export function ChartLayoutBlock({ el, chartColors, onChange }: Props) {
  const p = el.props;

  function setProp(path: string, value: unknown) {
    const props = { ...p, [path]: value };
    if (value === undefined) delete props[path];
    onChange({ ...el, props });
  }

  function numberField(f: ChartNumberProp) {
    return (
      <label key={f.path} className={styles.propField}>
        <span>{f.label}</span>
        <DraftInput
          type="number"
          step={f.step}
          min={f.min}
          max={f.max}
          value={p[f.path] === undefined ? "" : Number(p[f.path])}
          placeholder="Auto"
          validate={blankOrNumber}
          onCommit={(v) => setProp(f.path, v.trim() === "" ? undefined : Number(v))}
        />
      </label>
    );
  }

  return (
    <div className={styles.uploadBlock}>
      <h3 className={styles.styleHeading}>Axes, bars and legend</h3>
      <p className={styles.panelHint}>
        Leave a box empty to keep the chart&apos;s own layout. Axis and bar settings apply to charts
        with bars, lines or a value axis.
      </p>
      <div className={styles.styleColorGrid}>
        <label className={styles.propField}>
          <span>Legend position</span>
          <select
            value={String(p.legend_position ?? "")}
            onChange={(e) => setProp("legend_position", e.target.value || undefined)}
          >
            {CHART_LEGEND_POSITIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className={styles.propField}>
          <span>Decimals</span>
          <select
            value={p.decimals === undefined ? "" : String(p.decimals)}
            onChange={(e) => setProp("decimals", e.target.value === "" ? undefined : Number(e.target.value))}
          >
            {CHART_DECIMALS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        {CHART_AXIS_PROPS.map(numberField)}
      </div>
      {isGaugeChart(p) && (
        <>
          <h3 className={styles.styleHeading}>Gauge bands</h3>
          <p className={styles.panelHint}>
            Band starts are in the gauge&apos;s own units: a ratio for SPI (e.g. 0.8), a percentage for
            completion. Starts that don&apos;t rise in order are ignored.
          </p>
          <div className={styles.styleColorGrid}>
            {GAUGE_NUMBER_PROPS.map(numberField)}
            {GAUGE_COLOR_PROPS.map((c) => (
              <label key={c.path} className={styles.propField}>
                <span>{c.label}</span>
                <input
                  type="color"
                  value={String(p[c.path] ?? (typeof chartColors?.[c.colorKey] === "string"
                    ? chartColors[c.colorKey] : "#000000"))}
                  onChange={(e) => setProp(c.path, e.target.value)}
                />
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
