"use client";

// The paper: guides (margin box, header/footer bands), master elements as
// non-interactive ghosts, then this page's own elements on top — each
// showing this report's real data (see ElementPreview) inside its box, not
// a rendered PDF image. A page is an editable "layer" of positioned
// elements, closer to Photoshop frames than a pixel-perfect page preview.
import { useEffect, useRef, useState } from "react";

import { contentBox, pageDimensions } from "@/lib/reportLayout";
import type {
  ChartSvgMap, LayoutElement, PageDesign, TableDataMap, TocCaptionsData, TocEntry,
} from "@/lib/reportLayout";
import type { AlignGuides, ResizeHandle } from "@/hooks/useCanvasInteraction";
import { RESIZE_HANDLES } from "@/hooks/useCanvasInteraction";
import { findSpec } from "@/lib/reportElements";
import { embedHtml } from "@/lib/reportEmbeds";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { CanvasElementView } from "./CanvasElementView";
import type { ElementAction } from "./CanvasElementView";
import styles from "./designer.module.css";

type Box = { x: number; y: number; w: number; h: number };

function boxesIntersect(r: Box, el: LayoutElement): boolean {
  return el.x < r.x + r.w && el.x + el.w > r.x && el.y < r.y + r.h && el.y + el.h > r.y;
}

function groupBoundingBox(els: LayoutElement[]): Box {
  const x0 = Math.min(...els.map((e) => e.x));
  const y0 = Math.min(...els.map((e) => e.y));
  const x1 = Math.max(...els.map((e) => e.x + e.w));
  const y1 = Math.max(...els.map((e) => e.y + e.h));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

/** The shared outline + resize handles drawn around a multi-selection —
 * individual members keep their own thin selected-outline (via
 * CanvasElementView's `selected`) but not their own handles (`showControls`
 * is false for all of them while this is up), so there's exactly one set of
 * resize handles for the group, not one per member stacked on top of each
 * other. The box itself is `pointer-events: none` (see designer.module.css)
 * — it necessarily covers every member beneath it, and if it ate clicks
 * itself, a shift-click meant to toggle one specific member back out of the
 * selection would always land on the box instead and never reach that
 * element. Dragging any member already moves the whole group (see
 * CanvasElementView/LayoutEditor's handleStartMove) — this box has no move
 * gesture of its own, only the resize handles opt back into pointer-events. */
function GroupSelectionBox({
  elements, scale, onStartResize,
}: {
  elements: LayoutElement[];
  scale: number;
  onStartResize: (e: React.PointerEvent, handle: ResizeHandle) => void;
}) {
  const box = groupBoundingBox(elements);
  return (
    <div
      className={styles.groupBox}
      style={{
        left: `${box.x * scale}px`,
        top: `${box.y * scale}px`,
        width: `${box.w * scale}px`,
        height: `${box.h * scale}px`,
      }}
    >
      {RESIZE_HANDLES.map((h) => (
        <span
          key={h}
          className={`${styles.handle} ${styles[`handle_${h}`]}`}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            e.stopPropagation();
            onStartResize(e, h);
          }}
        />
      ))}
      <span className={styles.sizeBadge}>{elements.length} elements</span>
    </div>
  );
}

interface Props {
  design: PageDesign;
  elements: LayoutElement[];
  masterElements?: LayoutElement[];
  scale: number;
  selectedIds: string[];
  showGuides: boolean;
  /** Alignment guide lines while dragging (Canva-style snap-to-content). */
  alignGuides?: AlignGuides | null;
  /** `additive` (shift/ctrl/cmd) toggles membership instead of replacing
   * the selection; `null` clears it (background click, empty marquee). */
  onSelect: (id: string | null, additive?: boolean) => void;
  /** A finished marquee drag — every element it touched, plus whether it
   * was shift/ctrl-held (add to the existing selection) or not (replace it). */
  onMarqueeSelect: (ids: string[], additive: boolean) => void;
  onStartMove: (e: React.PointerEvent, el: LayoutElement) => void;
  onStartResize: (e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) => void;
  onStartRotate?: (e: React.PointerEvent, el: LayoutElement) => void;
  /** Resizes the whole current selection as one group — see
   * GroupSelectionBox. Present only when >1 element is selected (moving a
   * group has no dedicated handler of its own — see that component's
   * docstring — so there's no matching onStartGroupMove here). */
  onStartGroupResize?: (e: React.PointerEvent, handle: ResizeHandle) => void;
  onAction: (action: ElementAction, id: string) => void;
  /** Drop from the palette — coordinates arrive in mm, already page-relative. */
  onDropSpec?: (specKey: string, xMm: number, yMm: number) => void;
  /** Commits an inline text edit (a table cell, TOC row, field value, or
   * plain text box double-clicked directly on the canvas) through the same
   * undo-tracked update path as the Properties panel — see LayoutEditor's
   * updateElement. Only wired to the live (non-ghost) elements below. */
  onElementChange?: (el: LayoutElement) => void;
  /** Present only in the report-level "Customize" tab. */
  liveData?: ReportData | null;
  /** This report's id — present only alongside liveData. Lets a description
   * element's inline image-embed control attach an upload to this report. */
  reportId?: string;
  pinnedItem?: RepeatItem | RepeatItem[] | null;
  /** Live, real per-chart previews — see useChartSvgs. */
  chartSvgs?: ChartSvgMap;
  /** Live, real per-table data — see useTableData. */
  tableData?: TableDataMap;
  /** Live, real "List of tables/figures/images" content — see
   * useTocEntries. */
  tocCaptions?: TocCaptionsData;
  /** False until chartSvgs/tableData/tocCaptions's first real response has
   * landed. */
  previewsReady?: boolean;
  /** Every page in the current draft with its real page number — see
   * ReportConfigurator. */
  tocEntries?: TocEntry[];
  /** This page's own id — a "toc" element on this page skips its own row. */
  ownPageId?: string;
}

export function CanvasPage({
  design, elements, masterElements = [], scale, selectedIds, showGuides, alignGuides,
  onSelect, onMarqueeSelect, onStartMove, onStartResize, onStartRotate, onStartGroupResize,
  onAction, onDropSpec, onElementChange, liveData, reportId, pinnedItem,
  chartSvgs, tableData, tocCaptions, previewsReady, tocEntries, ownPageId,
}: Props) {
  const { w, h } = pageDimensions(design);
  const box = contentBox(design);
  const borderOffset = design.border_offset_mm ?? design.margin_mm;
  const pxWidth = w * scale;
  const multiSelected = selectedIds.length > 1;
  const selectedElements = elements.filter((e) => selectedIds.includes(e.id));

  const paperRef = useRef<HTMLDivElement>(null);
  // A drag-to-select rectangle on empty canvas — refs so the window
  // listeners (bound once, not per pixel of movement) always read the
  // latest gesture without needing to rebind; `marqueeVisual` state only
  // drives the rectangle's own rendering.
  const marqueeStart = useRef<{ x: number; y: number; additive: boolean } | null>(null);
  const marqueeNow = useRef<Box | null>(null);
  const [marqueeVisual, setMarqueeVisual] = useState<Box | null>(null);

  useEffect(() => {
    function onMove(event: PointerEvent) {
      const start = marqueeStart.current;
      if (!start || !paperRef.current) return;
      const rect = paperRef.current.getBoundingClientRect();
      const curX = (event.clientX - rect.left) / scale;
      const curY = (event.clientY - rect.top) / scale;
      const next: Box = {
        x: Math.min(start.x, curX), y: Math.min(start.y, curY),
        w: Math.abs(curX - start.x), h: Math.abs(curY - start.y),
      };
      marqueeNow.current = next;
      setMarqueeVisual(next);
    }
    function onUp() {
      const start = marqueeStart.current;
      const rect = marqueeNow.current;
      marqueeStart.current = null;
      marqueeNow.current = null;
      setMarqueeVisual(null);
      if (!start) return;
      // Below ~1mm of drag reads as a click, not a marquee — clears the
      // selection (unless additive, where a "click" on empty space doing
      // nothing is the less surprising behavior).
      if (!rect || (rect.w < 1 && rect.h < 1)) {
        if (!start.additive) onSelect(null);
        return;
      }
      const hits = elements.filter((el) => boxesIntersect(rect, el)).map((el) => el.id);
      if (hits.length) onMarqueeSelect(hits, start.additive);
      else if (!start.additive) onSelect(null);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [scale, elements, onSelect, onMarqueeSelect]);

  return (
    <div
      ref={paperRef}
      className={styles.paper}
      style={{
        width: `${pxWidth}px`,
        height: `${h * scale}px`,
        background: design.background,
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        // Without this, the same drag also kicks off the browser's native
        // text selection over any text it crosses (header/footer, field
        // labels, TOC rows...) — it paints its own blue highlight right on
        // top of the marquee rectangle below, which reads as "dragging to
        // select is selecting random text" rather than what it actually is.
        e.preventDefault();
        const rect = paperRef.current!.getBoundingClientRect();
        marqueeStart.current = {
          x: (e.clientX - rect.left) / scale,
          y: (e.clientY - rect.top) / scale,
          additive: e.shiftKey || e.metaKey || e.ctrlKey,
        };
      }}
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

        // Dropping a table/chart directly onto an actively-edited
        // description's rich text (see ElementPreview's DescriptionPreview
        // — only the one currently being edited is ever a real
        // contenteditable) inserts it as an inline embed right there,
        // instead of creating a new floating page element — same drag
        // gesture as any other palette item, different landing spot.
        const editableTarget = (e.target as HTMLElement)
          .closest('[contenteditable="true"]') as HTMLElement | null;
        if (editableTarget) {
          const spec = findSpec(key);
          if (spec && (spec.type === "table" || spec.type === "chart")) {
            const range = document.caretRangeFromPoint?.(e.clientX, e.clientY);
            const sel = window.getSelection();
            if (range && sel) {
              sel.removeAllRanges();
              sel.addRange(range);
            }
            editableTarget.focus();
            document.execCommand(
              "insertHTML", false, `${embedHtml(spec.type, spec.props ?? {}, spec.label)}<p><br></p>`,
            );
            editableTarget.dispatchEvent(new InputEvent("input", { bubbles: true }));
            return;
          }
        }

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
          tableData={tableData}
          tocCaptions={tocCaptions}
          previewsReady={previewsReady}
          tocEntries={tocEntries}
          ownPageId={ownPageId}
        />
      ))}

      {[...elements].sort((a, b) => a.z - b.z).map((el) => (
        <CanvasElementView
          key={el.id}
          el={el}
          scale={scale}
          selected={selectedIds.includes(el.id)}
          showControls={!multiSelected}
          onSelect={onSelect}
          onStartMove={onStartMove}
          onStartResize={onStartResize}
          onStartRotate={multiSelected ? undefined : onStartRotate}
          onAction={onAction}
          onElementChange={onElementChange}
          liveData={liveData}
          reportId={reportId}
          pinnedItem={pinnedItem}
          chartSvgs={chartSvgs}
          tableData={tableData}
          tocCaptions={tocCaptions}
          previewsReady={previewsReady}
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

      {multiSelected && onStartGroupResize && (
        <GroupSelectionBox
          elements={selectedElements}
          scale={scale}
          onStartResize={onStartGroupResize}
        />
      )}

      {marqueeVisual && (
        <div
          className={styles.marqueeBox}
          style={{
            left: `${marqueeVisual.x * scale}px`,
            top: `${marqueeVisual.y * scale}px`,
            width: `${marqueeVisual.w * scale}px`,
            height: `${marqueeVisual.h * scale}px`,
          }}
        />
      )}
    </div>
  );
}
