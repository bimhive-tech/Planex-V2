"use client";

// One placed element: its visual, the selection outline, eight resize handles,
// and the Canva-style ⋯ menu. Position/size are mm → px via `scale`.
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { RESIZE_HANDLES } from "@/hooks/useCanvasInteraction";
import type { ResizeHandle } from "@/hooks/useCanvasInteraction";
import type { ChartSvgMap, LayoutElement, ReportLabels, TableDataMap, TocCaptionsData, TocEntry } from "@/lib/reportLayout";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { ElementPreview } from "./ElementPreview";
import styles from "./designer.module.css";

export type ElementAction = "duplicate" | "delete" | "forward" | "backward";

interface Props {
  el: LayoutElement;
  scale: number;
  selected: boolean;
  /** True unless this element is one of several selected at once — a group
   * selection shows one shared bounding-box outline with its own handles
   * (see CanvasPage's GroupSelectionBox) instead of every member drawing
   * its own resize handles/rotate stem/⋯ menu on top of each other. The
   * element's own selected-outline still shows either way. */
  showControls?: boolean;
  /** Master elements are shown behind page content and aren't editable here. */
  ghost?: boolean;
  /** `additive` is a shift/ctrl/cmd click — toggle this element's membership
   * in the current selection instead of replacing it. */
  onSelect: (id: string, additive: boolean) => void;
  onStartMove: (e: React.PointerEvent, el: LayoutElement) => void;
  onStartResize: (e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) => void;
  onStartRotate?: (e: React.PointerEvent, el: LayoutElement) => void;
  onAction: (action: ElementAction, id: string) => void;
  /** Commits an inline text edit — see CanvasPage's doc comment. Undefined
   * for ghost elements (the other tab's background reference isn't
   * directly editable there). */
  onElementChange?: (el: LayoutElement) => void;
  /** Present only in the report-level "Customize" tab. */
  liveData?: ReportData | null;
  /** This report's id — lets a description element's inline image-embed
   * control attach an upload to this report. */
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
  /** This report's effective label dict — see ReportLabels. */
  labels?: ReportLabels;
  /** Every page in the current draft with its real page number — see
   * ReportConfigurator. */
  tocEntries?: TocEntry[];
  /** The page this element is being drawn on — see ElementPreview. */
  ownPageId?: string;
}

export function CanvasElementView({
  el, scale, selected, showControls = true, ghost, onSelect, onStartMove, onStartResize, onStartRotate, onAction,
  onElementChange, liveData, reportId, pinnedItem, chartSvgs, tableData, tocCaptions, previewsReady, labels,
  tocEntries, ownPageId,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  const style: React.CSSProperties = {
    left: `${el.x * scale}px`,
    top: `${el.y * scale}px`,
    width: `${el.w * scale}px`,
    height: `${el.h * scale}px`,
    zIndex: el.z,
    transform: el.rotation ? `rotate(${el.rotation}deg)` : undefined,
  };

  if (ghost) {
    // A template's master header/footer is a faded reference here (not
    // directly editable on this tab); on a report it's real, final content
    // — full opacity, so the page reads as the actual page, not a mockup.
    const ghostClass = liveData ? styles.elementGhostReal : styles.elementGhost;
    return (
      <div className={`${styles.element} ${ghostClass}`} style={style} aria-hidden="true">
        <ElementPreview
          el={el} scale={scale} liveData={liveData} pinnedItem={pinnedItem}
          chartSvgs={chartSvgs} tableData={tableData} tocCaptions={tocCaptions} previewsReady={previewsReady}
          labels={labels} tocEntries={tocEntries} ownPageId={ownPageId}
        />
      </div>
    );
  }

  return (
    <div
      data-canvas-element
      className={`${styles.element} ${selected ? styles.elementSelected : ""}`}
      style={style}
      onPointerDown={(e) => {
        // Left button only — right-click should not start a drag.
        if (e.button !== 0) return;
        // A press that lands on a real control INSIDE the element (a custom
        // table's cell input, its row/column buttons, the rich-text editor)
        // must still SELECT the element — it just must not start a drag, or
        // the click-to-place-a-caret gesture would move the box instead.
        // Those controls used to stopPropagation to avoid the drag, which
        // meant the press never reached here at all: clicking a table's cells
        // (i.e. nearly its whole surface) left the element unselected and the
        // Properties panel stuck on its empty state, so none of that table's
        // own styling controls could be reached while editing it
        // (2026-08-30, found reviewing the row/column editing flow).
        if ((e.target as HTMLElement).closest("input, textarea, select, button, [contenteditable]")) {
          if (!selected) onSelect(el.id, false);
          return;
        }
        const additive = e.shiftKey || e.metaKey || e.ctrlKey;
        if (additive) {
          // Composing a multi-selection — toggle membership only. Starting a
          // move here too would make a shift-click also drag, which reads
          // as an accidental nudge rather than a deliberate selection change.
          onSelect(el.id, true);
          return;
        }
        // Already part of a multi-selection: keep the whole group selected
        // and drag it as one (grabbing any member moves all of them) — only
        // a plain click on an element outside the current selection
        // collapses it down to just that one.
        if (!selected) onSelect(el.id, false);
        onStartMove(e, el);
      }}
      role="button"
      tabIndex={0}
      aria-label={`${el.type} element`}
      onKeyDown={(e) => {
        // Only handle Enter/Space as this div's own "activate like a button"
        // key (role="button" a11y pattern) when IT is the actual key target
        // — not when the event bubbled up from a focused descendant. Without
        // this guard, every space/enter typed into a nested contentEditable
        // (e.g. the Description element's rich-text editor, rendered inside
        // this same wrapper) bubbled here and got preventDefault()'d, which
        // silently blocks the browser from ever inserting the character —
        // found live: typing "Test description text" produced
        // "Testdescriptiontext", every space eaten (2026-08-26).
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(el.id, false);
        }
      }}
    >
      <ElementPreview
        el={el} scale={scale} liveData={liveData} reportId={reportId} pinnedItem={pinnedItem}
        chartSvgs={chartSvgs} tableData={tableData} tocCaptions={tocCaptions} previewsReady={previewsReady}
        labels={labels} tocEntries={tocEntries} ownPageId={ownPageId} onElementChange={onElementChange}
      />

      {selected && showControls && (
        <>
          {RESIZE_HANDLES.map((h) => (
            <span
              key={h}
              className={`${styles.handle} ${styles[`handle_${h}`]}`}
              onPointerDown={(e) => {
                if (e.button !== 0) return;
                onStartResize(e, el, h);
              }}
            />
          ))}

          {onStartRotate && (
            <span
              className={styles.rotateHandleStem}
              aria-hidden="true"
            >
              <span
                className={styles.rotateHandle}
                role="button"
                aria-label="Rotate element"
                onPointerDown={(e) => {
                  if (e.button !== 0) return;
                  onStartRotate(e, el);
                }}
              >
                <Icon name="refresh" size={11} />
              </span>
            </span>
          )}

          <div className={styles.elementMenu} ref={menuRef}>
            <button
              type="button"
              className={styles.menuTrigger}
              aria-label="Element options"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((v) => !v);
              }}
            >
              ⋯
            </button>
            {menuOpen && (
              <div className={styles.menuPopover} onPointerDown={(e) => e.stopPropagation()}>
                <button type="button" onClick={() => { onAction("duplicate", el.id); setMenuOpen(false); }}>
                  <Icon name="copy" size={14} /> Duplicate
                </button>
                <button type="button" onClick={() => { onAction("forward", el.id); setMenuOpen(false); }}>
                  <Icon name="chevronDown" size={14} className={styles.flipUp} /> Bring forward
                </button>
                <button type="button" onClick={() => { onAction("backward", el.id); setMenuOpen(false); }}>
                  <Icon name="chevronDown" size={14} /> Send backward
                </button>
                <button
                  type="button"
                  className={styles.menuDanger}
                  onClick={() => { onAction("delete", el.id); setMenuOpen(false); }}
                >
                  <Icon name="trash" size={14} /> Delete
                </button>
              </div>
            )}
          </div>

          <span className={styles.sizeBadge}>
            {Math.round(el.w)} × {Math.round(el.h)} mm
          </span>
        </>
      )}
    </div>
  );
}
