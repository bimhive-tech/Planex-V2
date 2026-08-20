"use client";

// Bottom thumbnail strip for the Report Configuration canvas (Phase 3's
// "Canva-style page strip"). Deliberately lightweight — a wireframe of each
// element's position/size/type, not a live render of its real chart/table
// data — so scrolling through a 50+ page report (a real zone-dashboard
// report easily has that many) stays instant. The main canvas above already
// shows the *active* page fully live; this is for "which page is that"
// navigation, not a second full preview.
import { pageDimensions } from "@/lib/reportLayout";
import type { LayoutPage, PageDesign } from "@/lib/reportLayout";
import { Icon } from "@/components/ui/Icon";
import styles from "./designer.module.css";

const THUMB_W = 56;

/** One flat color per element type — enough to read a page's rough layout
 * (a table-heavy page looks different from a chart-heavy one) without
 * needing that element's real content. */
const TYPE_COLORS: Record<string, string> = {
  text: "#94a3b8",
  field: "#94a3b8",
  image: "#60a5fa",
  logo: "#60a5fa",
  rect: "#c4b5fd",
  ellipse: "#c4b5fd",
  line: "#c4b5fd",
  table: "#34d399",
  chart: "#fb923c",
  toc: "#f472b6",
};

interface Props {
  pages: LayoutPage[];
  design: PageDesign;
  activeId: string;
  onSelect: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
}

export function PageStrip({ pages, design, activeId, onSelect, onDuplicate, onDelete, onAdd }: Props) {
  return (
    <div className={styles.pageStrip} aria-label="Pages">
      {pages.map((page, i) => {
        // This page's own orientation override (see ReportConfigurator's
        // effectiveDesign) — a landscape-pinned page reads as a wide
        // thumbnail here too, not silently rendered as if it were portrait.
        const { w, h } = pageDimensions(page.orientation ? { ...design, orientation: page.orientation } : design);
        const thumbH = (h / w) * THUMB_W;
        return (
        <div
          key={page.id}
          className={`${styles.pageStripItem} ${page.id === activeId ? styles.pageStripItemActive : ""}`}
        >
          <button
            type="button"
            className={styles.pageStripThumb}
            style={{ width: `${THUMB_W}px`, height: `${thumbH}px`, background: design.background }}
            onClick={() => onSelect(page.id)}
            title={page.name}
          >
            {page.elements.map((el) => (
              <span
                key={el.id}
                className={styles.pageStripEl}
                style={{
                  left: `${(el.x / w) * 100}%`,
                  top: `${(el.y / h) * 100}%`,
                  width: `${Math.max(2, (el.w / w) * 100)}%`,
                  height: `${Math.max(2, (el.h / h) * 100)}%`,
                  background: TYPE_COLORS[el.type] ?? "#cbd5e1",
                }}
              />
            ))}
          </button>
          <div className={styles.pageStripFoot}>
            <span className={styles.pageStripNumber}>{i + 1}</span>
            <button
              type="button" className={styles.pageStripAction}
              onClick={() => onDuplicate(page.id)} title="Duplicate page" aria-label="Duplicate page"
            >
              <Icon name="copy" size={10} />
            </button>
            <button
              type="button" className={styles.pageStripAction}
              onClick={() => onDelete(page.id)} title="Delete page" aria-label="Delete page"
              disabled={pages.length === 1}
            >
              <Icon name="trash" size={10} />
            </button>
          </div>
        </div>
        );
      })}
      <button type="button" className={styles.pageStripAdd} onClick={onAdd} title="Add a new page">
        <Icon name="plus" size={16} />
      </button>
    </div>
  );
}
