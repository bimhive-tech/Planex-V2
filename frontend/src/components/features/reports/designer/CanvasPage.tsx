"use client";

// The paper: guides (margin box, header/footer bands), master elements as
// non-interactive ghosts, then this page's own elements on top — each
// showing this report's real data (see ElementPreview) inside its box, not
// a rendered PDF image. A page is an editable "layer" of positioned
// elements, closer to Photoshop frames than a pixel-perfect page preview.
import { contentBox, pageDimensions } from "@/lib/reportLayout";
import type { ChartSvgMap, LayoutElement, PageDesign, TableImageMap, TocEntry } from "@/lib/reportLayout";
import type { AlignGuides, ResizeHandle } from "@/hooks/useCanvasInteraction";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { CanvasElementView } from "./CanvasElementView";
import type { ElementAction } from "./CanvasElementView";
import styles from "./designer.module.css";

interface Props {
  design: PageDesign;
  elements: LayoutElement[];
  masterElements?: LayoutElement[];
  scale: number;
  selectedId: string | null;
  showGuides: boolean;
  /** Alignment guide lines while dragging (Canva-style snap-to-content). */
  alignGuides?: AlignGuides | null;
  onSelect: (id: string | null) => void;
  onStartMove: (e: React.PointerEvent, el: LayoutElement) => void;
  onStartResize: (e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) => void;
  onStartRotate?: (e: React.PointerEvent, el: LayoutElement) => void;
  onAction: (action: ElementAction, id: string) => void;
  /** Drop from the palette — coordinates arrive in mm, already page-relative. */
  onDropSpec?: (specKey: string, xMm: number, yMm: number) => void;
  /** Present only in the report-level "Customize" tab. */
  liveData?: ReportData | null;
  pinnedItem?: RepeatItem | RepeatItem[] | null;
  /** Live, real per-chart previews — see useChartSvgs. */
  chartSvgs?: ChartSvgMap;
  /** Live, real per-table previews — see useTableImages. */
  tableImages?: TableImageMap;
  /** Every page in the current draft with its real page number — see
   * ReportConfigurator. */
  tocEntries?: TocEntry[];
  /** This page's own id — a "toc" element on this page skips its own row. */
  ownPageId?: string;
}

export function CanvasPage({
  design, elements, masterElements = [], scale, selectedId, showGuides, alignGuides,
  onSelect, onStartMove, onStartResize, onStartRotate, onAction, onDropSpec, liveData, pinnedItem,
  chartSvgs, tableImages, tocEntries, ownPageId,
}: Props) {
  const { w, h } = pageDimensions(design);
  const box = contentBox(design);
  const borderOffset = design.border_offset_mm ?? design.margin_mm;
  const pxWidth = w * scale;

  return (
    <div
      className={styles.paper}
      style={{
        width: `${pxWidth}px`,
        height: `${h * scale}px`,
        background: design.background,
      }}
      onPointerDown={() => onSelect(null)}
      onDragOver={(e) => {
        if (!onDropSpec) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(e) => {
        if (!onDropSpec) return;
        e.preventDefault();
        const key = e.dataTransfer.getData("text/planex-element");
        if (!key) return;
        const rect = e.currentTarget.getBoundingClientRect();
        onDropSpec(key, (e.clientX - rect.left) / scale, (e.clientY - rect.top) / scale);
      }}
    >
      {design.show_border && (
        <div
          className={styles.pageBorder}
          style={{
            left: `${borderOffset * scale}px`,
            top: `${borderOffset * scale}px`,
            width: `${Math.max(0, w - borderOffset * 2) * scale}px`,
            height: `${Math.max(0, h - borderOffset * 2) * scale}px`,
          }}
        />
      )}

      {showGuides && (
        <>
          <div
            className={styles.guideMargin}
            style={{
              left: `${design.margin_mm * scale}px`,
              top: `${design.margin_mm * scale}px`,
              width: `${Math.max(0, w - design.margin_mm * 2) * scale}px`,
              height: `${Math.max(0, h - design.margin_mm * 2) * scale}px`,
            }}
          />
          {design.show_header && (
            <div
              className={styles.guideBand}
              style={{
                left: `${design.margin_mm * scale}px`,
                top: `${design.margin_mm * scale}px`,
                width: `${Math.max(0, w - design.margin_mm * 2) * scale}px`,
                height: `${design.header_mm * scale}px`,
              }}
            >
              <span>Header · {design.header_mm}mm</span>
            </div>
          )}
          {design.show_footer && (
            <div
              className={styles.guideBand}
              style={{
                left: `${design.margin_mm * scale}px`,
                top: `${(h - design.margin_mm - design.footer_mm) * scale}px`,
                width: `${Math.max(0, w - design.margin_mm * 2) * scale}px`,
                height: `${design.footer_mm * scale}px`,
              }}
            >
              <span>Footer · {design.footer_mm}mm</span>
            </div>
          )}
          <div
            className={styles.guideContent}
            style={{
              left: `${box.x * scale}px`,
              top: `${box.y * scale}px`,
              width: `${box.w * scale}px`,
              height: `${box.h * scale}px`,
            }}
          />
        </>
      )}

      {masterElements.map((el) => (
        <CanvasElementView
          key={`master-${el.id}`}
          el={el}
          scale={scale}
          selected={false}
          ghost
          onSelect={() => {}}
          onStartMove={() => {}}
          onStartResize={() => {}}
          onAction={() => {}}
          liveData={liveData}
          pinnedItem={pinnedItem}
          chartSvgs={chartSvgs}
          tableImages={tableImages}
          tocEntries={tocEntries}
          ownPageId={ownPageId}
        />
      ))}

      {[...elements].sort((a, b) => a.z - b.z).map((el) => (
        <CanvasElementView
          key={el.id}
          el={el}
          scale={scale}
          selected={el.id === selectedId}
          onSelect={onSelect}
          onStartMove={onStartMove}
          onStartResize={onStartResize}
          onStartRotate={onStartRotate}
          onAction={onAction}
          liveData={liveData}
          pinnedItem={pinnedItem}
          chartSvgs={chartSvgs}
          tableImages={tableImages}
          tocEntries={tocEntries}
          ownPageId={ownPageId}
        />
      ))}

      {alignGuides?.x.map((x) => (
        <div key={`vg-${x}`} className={styles.alignGuideV} style={{ left: `${x * scale}px` }} />
      ))}
      {alignGuides?.y.map((y) => (
        <div key={`hg-${y}`} className={styles.alignGuideH} style={{ top: `${y * scale}px` }} />
      ))}
    </div>
  );
}
