"use client";

// Tab 1 — Page Designer. The master-slide equivalent: paper size, margins and
// the header/footer bands (shown to scale so you can see exactly how much room
// they take), plus master elements that repeat on every page of the report.
import { PAGE_SIZES } from "@/lib/reportLayout";
import type { PageDesign, PageSizeKey } from "@/lib/reportLayout";
import { LayoutEditor } from "./LayoutEditor";
import styles from "./designer.module.css";

interface Props {
  design: PageDesign;
  /** Updater form so rapid successive edits can't clobber each other. */
  onChange: (updater: (prev: PageDesign) => PageDesign) => void;
}

export function PageDesigner({ design, onChange }: Props) {
  function set<K extends keyof PageDesign>(key: K, value: PageDesign[K]) {
    onChange((prev) => ({ ...prev, [key]: value }));
  }

  const setup = (
    <section className={styles.setupPanel} aria-label="Page setup">
      <h2 className={styles.panelTitle}>Page setup</h2>
      <p className={styles.panelHint}>Applies to every page in the report.</p>

      <label className={styles.propField}>
        <span>Paper size</span>
        <select value={design.size} onChange={(e) => set("size", e.target.value as PageSizeKey)}>
          {Object.entries(PAGE_SIZES).map(([key, s]) => (
            <option key={key} value={key}>{s.label}</option>
          ))}
        </select>
      </label>

      <label className={styles.propField}>
        <span>Orientation</span>
        <select
          value={design.orientation}
          onChange={(e) => set("orientation", e.target.value as PageDesign["orientation"])}
        >
          <option value="portrait">Portrait</option>
          <option value="landscape">Landscape</option>
        </select>
      </label>

      <label className={styles.propField}>
        <span>Margin (mm)</span>
        <input
          type="number" min={0} max={60} step={1} value={design.margin_mm}
          onChange={(e) => set("margin_mm", Number(e.target.value))}
        />
      </label>

      <label className={styles.propToggle}>
        <input
          type="checkbox" checked={design.show_header}
          onChange={(e) => set("show_header", e.target.checked)}
        />
        <span>Header band</span>
      </label>
      {design.show_header && (
        <label className={styles.propField}>
          <span>Header height (mm)</span>
          <input
            type="number" min={0} max={80} step={1} value={design.header_mm}
            onChange={(e) => set("header_mm", Number(e.target.value))}
          />
        </label>
      )}

      <label className={styles.propToggle}>
        <input
          type="checkbox" checked={design.show_footer}
          onChange={(e) => set("show_footer", e.target.checked)}
        />
        <span>Footer band</span>
      </label>
      {design.show_footer && (
        <label className={styles.propField}>
          <span>Footer height (mm)</span>
          <input
            type="number" min={0} max={80} step={1} value={design.footer_mm}
            onChange={(e) => set("footer_mm", Number(e.target.value))}
          />
        </label>
      )}

      <label className={styles.propToggle}>
        <input
          type="checkbox" checked={design.show_border}
          onChange={(e) => set("show_border", e.target.checked)}
        />
        <span>Page border</span>
      </label>

      <label className={styles.propField}>
        <span>Page background</span>
        <input
          type="color" value={design.background}
          onChange={(e) => set("background", e.target.value)}
        />
      </label>
    </section>
  );

  return (
    <LayoutEditor
      design={design}
      elements={design.master_elements}
      onElementsChange={(updater) =>
        onChange((prev) => ({ ...prev, master_elements: updater(prev.master_elements) }))
      }
      leftHeader={setup}
      emptyHint="Anything you place here repeats on every page — logos, header text, page numbers."
    />
  );
}
