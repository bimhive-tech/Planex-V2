"use client";

// Shared editing surface for both builder tabs: palette on the left, paper in
// the middle, inspector on the right — plus all the element CRUD (add, move,
// resize, duplicate, re-order, delete) and zoom.
import { useMemo, useState } from "react";

import { useCanvasInteraction } from "@/hooks/useCanvasInteraction";
import { createElement, findSpec } from "@/lib/reportElements";
import { clampToPage, contentBox, newElementId, roundMm } from "@/lib/reportLayout";
import type { LayoutElement, PageDesign } from "@/lib/reportLayout";
import { CanvasPage } from "./CanvasPage";
import type { ElementAction } from "./CanvasElementView";
import { ElementInspector } from "./ElementInspector";
import { ElementPalette } from "./ElementPalette";
import styles from "./designer.module.css";

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5];
/** Base pixels-per-mm at 100% — A4 portrait then reads ~460px wide. */
const BASE_SCALE = 2.2;

interface Props {
  design: PageDesign;
  elements: LayoutElement[];
  /**
   * Takes an updater, not an array: two edits in the same tick (a fast
   * double-click on the palette) would otherwise both read the same stale
   * `elements` prop and the second would drop the first.
   */
  onElementsChange: (updater: (prev: LayoutElement[]) => LayoutElement[]) => void;
  /** Rendered above the palette (page setup, or the page list). */
  leftHeader?: React.ReactNode;
  /** Master elements drawn as ghosts behind the editable ones. */
  masterElements?: LayoutElement[];
  emptyHint?: string;
}

export function LayoutEditor({
  design, elements, onElementsChange, leftHeader, masterElements, emptyHint,
}: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [showGuides, setShowGuides] = useState(true);
  const scale = BASE_SCALE * zoom;

  const { draft, startMove, startResize } = useCanvasInteraction({
    scale,
    design,
    onCommit: (el) => onElementsChange((prev) => prev.map((e) => (e.id === el.id ? el : e))),
  });

  // While a gesture is live the draft stands in for the real element so the
  // canvas moves at pointer speed without re-rendering the whole builder.
  const rendered = useMemo(
    () => (draft ? elements.map((e) => (e.id === draft.id ? draft : e)) : elements),
    [elements, draft],
  );

  const selected = rendered.find((e) => e.id === selectedId) ?? null;

  const topZ = (list: LayoutElement[]) => list.reduce((max, e) => Math.max(max, e.z), 0);

  function addSpec(specKey: string, xMm?: number, yMm?: number) {
    const spec = findSpec(specKey);
    if (!spec) return;
    const box = contentBox(design);
    const dropped = xMm !== undefined && yMm !== undefined;
    // Id is generated up front so selection can target it; position and z are
    // resolved against the freshest list inside the updater.
    const id = newElementId();
    onElementsChange((prev) => {
      // Dropped: centre on the cursor. Clicked: land in the content box, but
      // cascade so repeated clicks don't stack invisibly on one another.
      const step = dropped ? 0 : (prev.length % 8) * 4;
      const x = dropped ? xMm! - spec.w / 2 : box.x + step;
      const y = dropped ? yMm! - spec.h / 2 : box.y + step;
      return [
        ...prev,
        clampToPage(
          { ...createElement(spec, roundMm(Math.max(0, x)), roundMm(Math.max(0, y)), topZ(prev) + 1), id },
          design,
        ),
      ];
    });
    setSelectedId(id);
  }

  function updateElement(next: LayoutElement) {
    onElementsChange((prev) =>
      prev.map((e) => (e.id === next.id ? clampToPage(next, design) : e)),
    );
  }

  function runAction(action: ElementAction, id: string) {
    if (action === "delete") {
      onElementsChange((prev) => prev.filter((e) => e.id !== id));
      setSelectedId(null);
      return;
    }
    if (action === "duplicate") {
      const copyId = newElementId();
      onElementsChange((prev) => {
        const el = prev.find((e) => e.id === id);
        if (!el) return prev;
        return [
          ...prev,
          clampToPage(
            { ...el, id: copyId, x: el.x + 5, y: el.y + 5, z: topZ(prev) + 1, props: { ...el.props } },
            design,
          ),
        ];
      });
      setSelectedId(copyId);
      return;
    }
    // Re-order: nudge z past the neighbour in that direction.
    const delta = action === "forward" ? 1 : -1;
    onElementsChange((prev) =>
      prev.map((e) => (e.id === id ? { ...e, z: Math.max(0, e.z + delta) } : e)),
    );
  }

  return (
    <div className={styles.editor}>
      <div className={styles.leftColumn}>
        {leftHeader}
        <ElementPalette onAdd={(key) => addSpec(key)} />
      </div>

      <main className={styles.canvasArea}>
        <div className={styles.canvasTools}>
          <div className={styles.toolGroup}>
            <button
              type="button"
              className={styles.toolBtn}
              onClick={() => setZoom((z) => ZOOMS[Math.max(0, ZOOMS.indexOf(z) - 1)] ?? z)}
              aria-label="Zoom out"
            >
              −
            </button>
            <span className={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
            <button
              type="button"
              className={styles.toolBtn}
              onClick={() => setZoom((z) => ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(z) + 1)] ?? z)}
              aria-label="Zoom in"
            >
              +
            </button>
          </div>
          <label className={styles.guideToggle}>
            <input type="checkbox" checked={showGuides} onChange={(e) => setShowGuides(e.target.checked)} />
            Guides
          </label>
          <span className={styles.canvasMeta}>
            {design.size} {design.orientation} · {elements.length} element{elements.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className={styles.canvasScroll}>
          <CanvasPage
            design={design}
            elements={rendered}
            masterElements={masterElements}
            scale={scale}
            selectedId={selectedId}
            showGuides={showGuides}
            onSelect={setSelectedId}
            onStartMove={startMove}
            onStartResize={startResize}
            onAction={runAction}
            onDropSpec={(key, x, y) => addSpec(key, x, y)}
          />
        </div>

        {elements.length === 0 && emptyHint && (
          <p className={styles.emptyHint}>{emptyHint}</p>
        )}
      </main>

      <ElementInspector el={selected} onChange={updateElement} />
    </div>
  );
}
