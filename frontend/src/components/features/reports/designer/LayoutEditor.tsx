"use client";

// Shared editing surface for both builder tabs: palette on the left, paper in
// the middle, inspector on the right — plus all the element CRUD (add, move,
// resize, rotate, duplicate, re-order, delete, copy/paste, undo) and zoom.
import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useCanvasInteraction } from "@/hooks/useCanvasInteraction";
import type { ResizeHandle } from "@/hooks/useCanvasInteraction";
import { createElement, findSpec } from "@/lib/reportElements";
import { clampToPage, contentBox, newElementId, roundMm } from "@/lib/reportLayout";
import type { ChartSvgMap, LayoutElement, PageDesign, TableDataMap, TocEntry } from "@/lib/reportLayout";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { CanvasPage } from "./CanvasPage";
import type { ElementAction } from "./CanvasElementView";
import { ElementInspector } from "./ElementInspector";
import { ElementPalette } from "./ElementPalette";
import styles from "./designer.module.css";

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5];
/** Base pixels-per-mm at 100% — A4 portrait then reads ~460px wide. */
const BASE_SCALE = 2.2;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;
/** How many past states Ctrl+Z can step back through, per editor session. */
const MAX_HISTORY = 50;

// A single, module-level clipboard: Page Designer and Report Configuration
// are two separate LayoutEditor mounts (only one visible at a time — see
// TemplateBuilder), so this is what lets you copy an element (or a whole
// multi-selected group) on one page — even the master — and paste it onto
// another without losing it on unmount.
let elementClipboard: LayoutElement[] | null = null;

/** True while focus is in a text field — Delete/Ctrl+Z etc. there should edit
 * the text, not the canvas selection. */
function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

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
  /** True when the active page is set to repeat — unlocks item-scoped
   * field/table/chart sources in the inspector (Report Configuration only). */
  repeating?: boolean;
  /** Present only in the report-level "Customize" tab. */
  liveData?: ReportData | null;
  /** This report's id — present only alongside liveData. Lets the inspector's
   * image-upload control attach an upload to this specific report. */
  reportId?: string;
  /** The real item (or chunk group) this page was expanded from — lets
   * item.* field/table/chart elements resolve real data instead of the
   * generic placeholder. null on a fixed page or an un-expanded template. */
  pinnedItem?: RepeatItem | RepeatItem[] | null;
  /** Live, real per-chart previews — see useChartSvgs. */
  chartSvgs?: ChartSvgMap;
  /** Live, real per-table data — see useTableData. */
  tableData?: TableDataMap;
  /** False until chartSvgs/tableData's first real response has landed. */
  previewsReady?: boolean;
  /** Every page in the current draft with its real page number — see
   * ReportConfigurator. */
  tocEntries?: TocEntry[];
  /** The active page's own id — a "toc" element on it skips its own row. */
  ownPageId?: string;
  /** Rendered below the canvas — the Report Configuration tab's page
   * thumbnail strip (see PageStrip). Undefined in the Page Designer, which
   * has only the one master, page-less surface. */
  bottomPanel?: React.ReactNode;
}

export function LayoutEditor({
  design, elements, onElementsChange, leftHeader, masterElements, emptyHint, repeating = false, liveData,
  pinnedItem, reportId, chartSvgs, tableData, previewsReady, tocEntries, ownPageId, bottomPanel,
}: Props) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [zoom, setZoom] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Margin/header/footer guides help while laying out a template, but on a
  // report (liveData present) they're just chrome between you and seeing
  // the page as its final, real self — off by default there, still
  // available via the checkbox for a moment of precise alignment.
  const [showGuides, setShowGuides] = useState(!liveData);
  const scale = BASE_SCALE * zoom;

  // Undo/redo history for this editor instance (Page Designer's master
  // elements and each Report Configuration page each get their own — a page
  // switch remounts LayoutEditor, so history doesn't follow you across pages).
  const undoStack = useRef<LayoutElement[][]>([]);
  const redoStack = useRef<LayoutElement[][]>([]);
  const elementsRef = useRef(elements);
  elementsRef.current = elements;
  // Stacks are refs (mutated without a re-render, by design — see `commit`),
  // so the toolbar buttons need their own trigger to know when to update
  // their enabled/disabled state.
  const [, setHistoryTick] = useState(0);
  const canUndo = undoStack.current.length > 0;
  const canRedo = redoStack.current.length > 0;

  /** Every mutation goes through here instead of onElementsChange directly,
   * so undo has a snapshot of what came before it. */
  function commit(updater: (prev: LayoutElement[]) => LayoutElement[]) {
    undoStack.current.push(elementsRef.current);
    if (undoStack.current.length > MAX_HISTORY) undoStack.current.shift();
    redoStack.current = [];
    onElementsChange(updater);
    setHistoryTick((t) => t + 1);
  }

  function undo() {
    const previous = undoStack.current.pop();
    if (!previous) return;
    redoStack.current.push(elementsRef.current);
    onElementsChange(() => previous);
    setHistoryTick((t) => t + 1);
  }

  function redo() {
    const next = redoStack.current.pop();
    if (!next) return;
    undoStack.current.push(elementsRef.current);
    onElementsChange(() => next);
    setHistoryTick((t) => t + 1);
  }

  const { draft, guides, startMove, startResize, startRotate } = useCanvasInteraction({
    scale,
    design,
    elements,
    masterElements,
    // A group drag/resize commits every moved member in the same updater —
    // one undo step for the whole gesture, not one per element.
    onCommit: (moved) => commit((prev) => {
      const byId = new Map(moved.map((e) => [e.id, e]));
      return prev.map((e) => byId.get(e.id) ?? e);
    }),
  });

  // While a gesture is live the draft elements stand in for the real ones
  // so the canvas moves at pointer speed without re-rendering the whole
  // builder — a group drag replaces every dragged member at once.
  const rendered = useMemo(() => {
    if (!draft) return elements;
    const byId = new Map(draft.map((e) => [e.id, e]));
    return elements.map((e) => byId.get(e.id) ?? e);
  }, [elements, draft]);

  const selected = selectedIds.length === 1 ? (rendered.find((e) => e.id === selectedIds[0]) ?? null) : null;

  /** Selects `id` — `additive` (shift/ctrl/cmd) toggles it in/out of the
   * current selection instead of replacing it. `null` clears everything
   * (background click, empty marquee, Escape). */
  function selectElement(id: string | null, additive = false) {
    if (id === null) { setSelectedIds([]); return; }
    if (!additive) { setSelectedIds([id]); return; }
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  /** A finished marquee drag — replaces or extends the selection with every
   * element the rectangle touched. */
  function selectMarquee(ids: string[], additive: boolean) {
    setSelectedIds((prev) => (additive ? Array.from(new Set([...prev, ...ids])) : ids));
  }

  // No startGroupMove counterpart — dragging any selected member already
  // moves the whole group (see handleStartMove below); a dedicated group
  // "grab the box body" gesture would have to sit on top of every member
  // it covers, which is exactly what broke shift-click-to-deselect a
  // member (see GroupSelectionBox's docstring in CanvasPage.tsx).
  function startGroupResize(e: React.PointerEvent, handle: ResizeHandle) {
    startResize(e, rendered.filter((el) => selectedIds.includes(el.id)), handle);
  }

  /** Grabbing any member of an already-selected group drags the whole
   * group; grabbing an element outside the current selection drags just
   * that one (CanvasElementView already collapsed the selection to it). */
  function handleStartMove(e: React.PointerEvent, el: LayoutElement) {
    const group = selectedIds.length > 1 && selectedIds.includes(el.id)
      ? rendered.filter((x) => selectedIds.includes(x.id))
      : [el];
    startMove(e, group);
  }

  // Per-element resize handles only render while a single element is
  // selected (see CanvasPage's showControls) — group resize goes through
  // startGroupResize instead — so this is always exactly one element.
  function handleStartResize(e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) {
    startResize(e, [el], handle);
  }

  const topZ = (list: LayoutElement[]) => list.reduce((max, e) => Math.max(max, e.z), 0);

  function addSpec(specKey: string, xMm?: number, yMm?: number) {
    const spec = findSpec(specKey);
    if (!spec) return;
    const box = contentBox(design);
    const dropped = xMm !== undefined && yMm !== undefined;
    // Id is generated up front so selection can target it; position and z are
    // resolved against the freshest list inside the updater.
    const id = newElementId();
    commit((prev) => {
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
    setSelectedIds([id]);
  }

  function updateElement(next: LayoutElement) {
    commit((prev) =>
      prev.map((e) => (e.id === next.id ? clampToPage(next, design) : e)),
    );
  }

  /** Pastes the whole clipboard (one element, or a copied multi-selection)
   * as a group, offset from where it was copied — and selects the new
   * copies, same as a single paste always has. */
  function pasteElement() {
    if (!elementClipboard || elementClipboard.length === 0) return;
    const sources = elementClipboard;
    const idMap = new Map(sources.map((s) => [s.id, newElementId()]));
    commit((prev) => {
      const baseZ = topZ(prev);
      const copies = sources.map((source, i) => clampToPage(
        {
          ...source, id: idMap.get(source.id)!, x: source.x + 5, y: source.y + 5,
          z: baseZ + i + 1, props: { ...source.props },
        },
        design,
      ));
      return [...prev, ...copies];
    });
    setSelectedIds(Array.from(idMap.values()));
  }

  function runAction(action: ElementAction, id: string) {
    if (action === "delete") {
      commit((prev) => prev.filter((e) => e.id !== id));
      setSelectedIds((prev) => prev.filter((x) => x !== id));
      return;
    }
    if (action === "duplicate") {
      const copyId = newElementId();
      commit((prev) => {
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
      setSelectedIds([copyId]);
      return;
    }
    // Re-order: nudge z past the neighbour in that direction.
    const delta = action === "forward" ? 1 : -1;
    commit((prev) =>
      prev.map((e) => (e.id === id ? { ...e, z: Math.max(0, e.z + delta) } : e)),
    );
  }

  /** Deletes every currently-selected element as one undo step. */
  function deleteSelection() {
    const ids = new Set(selectedIds);
    commit((prev) => prev.filter((e) => !ids.has(e.id)));
    setSelectedIds([]);
  }

  /** Copies the whole current selection (one element, or a group) to the
   * shared clipboard — see `pasteElement`. */
  function copySelection() {
    const ids = new Set(selectedIds);
    const els = elementsRef.current.filter((e) => ids.has(e.id));
    if (els.length) elementClipboard = els.map((e) => ({ ...e, props: { ...e.props } }));
  }

  // Keyboard shortcuts: Delete/Backspace, Ctrl/Cmd+C/V, Ctrl/Cmd+Z (+Shift for redo).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return;
      const mod = event.ctrlKey || event.metaKey;

      if ((event.key === "Delete" || event.key === "Backspace") && selectedIds.length) {
        event.preventDefault();
        deleteSelection();
        return;
      }
      if (event.key === "Escape" && selectedIds.length) {
        setSelectedIds([]);
        return;
      }
      if (mod && event.key.toLowerCase() === "c" && selectedIds.length) {
        copySelection();
        return;
      }
      if (mod && event.key.toLowerCase() === "v") {
        event.preventDefault();
        pasteElement();
        return;
      }
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedIds, design, elements, onElementsChange]);

  // Shift+scroll to zoom (Canva/Figma convention) — a plain scroll still
  // pans the canvas natively, `.canvasScroll`'s own overflow:auto already
  // does that for free. Needs a real (non-passive) listener via a ref: React
  // registers onWheel as passive by default, which silently drops
  // preventDefault and lets the page scroll *and* zoom at once.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    function onWheel(e: WheelEvent) {
      if (!e.shiftKey) return;
      e.preventDefault();
      setZoom((z) => {
        const raw = z - e.deltaY * 0.001;
        const clamped = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, raw));
        return Math.round(clamped * 100) / 100; // 2 decimal places — smooth, not jittery
      });
    }
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

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
              onClick={undo}
              disabled={!canUndo}
              aria-label="Undo"
              title="Undo (Ctrl+Z)"
            >
              <Icon name="undo" size={14} />
            </button>
            <button
              type="button"
              className={styles.toolBtn}
              onClick={redo}
              disabled={!canRedo}
              aria-label="Redo"
              title="Redo (Ctrl+Shift+Z)"
            >
              <Icon name="redo" size={14} />
            </button>
          </div>
          <div className={styles.toolGroup}>
            <button
              type="button"
              className={styles.toolBtn}
              // Nearest step below the current zoom, not ZOOMS.indexOf — shift+scroll
              // leaves zoom at an arbitrary value between steps, where indexOf would
              // find nothing and silently snap all the way to the smallest step.
              onClick={() => setZoom((z) => [...ZOOMS].reverse().find((s) => s < z - 0.001) ?? ZOOMS[0])}
              aria-label="Zoom out"
            >
              −
            </button>
            <span className={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
            <button
              type="button"
              className={styles.toolBtn}
              onClick={() => setZoom((z) => ZOOMS.find((s) => s > z + 0.001) ?? ZOOMS[ZOOMS.length - 1])}
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

        <div className={styles.canvasScroll} ref={scrollRef}>
          <CanvasPage
            design={design}
            elements={rendered}
            masterElements={masterElements}
            scale={scale}
            selectedIds={selectedIds}
            showGuides={showGuides}
            alignGuides={guides}
            onSelect={selectElement}
            onMarqueeSelect={selectMarquee}
            onStartMove={handleStartMove}
            onStartResize={handleStartResize}
            onStartRotate={startRotate}
            onStartGroupResize={startGroupResize}
            onAction={runAction}
            onDropSpec={(key, x, y) => addSpec(key, x, y)}
            onElementChange={updateElement}
            liveData={liveData}
            pinnedItem={pinnedItem}
            chartSvgs={chartSvgs}
            tableData={tableData}
            previewsReady={previewsReady}
            tocEntries={tocEntries}
            ownPageId={ownPageId}
          />
        </div>

        {elements.length === 0 && emptyHint && (
          <p className={styles.emptyHint}>{emptyHint}</p>
        )}

        {bottomPanel}
      </main>

      <ElementInspector
        el={selected}
        onChange={updateElement}
        repeating={repeating}
        reportId={reportId}
        selectedCount={selectedIds.length}
        onDeleteSelection={deleteSelection}
      />
    </div>
  );
}
