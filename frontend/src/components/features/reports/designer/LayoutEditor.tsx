"use client";

// Shared editing surface for both builder tabs: palette on the left, paper in
// the middle, inspector on the right — plus all the element CRUD (add, move,
// resize, rotate, duplicate, re-order, delete, copy/paste, undo) and zoom.
import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useCanvasInteraction } from "@/hooks/useCanvasInteraction";
import { createElement, findSpec } from "@/lib/reportElements";
import { clampToPage, contentBox, newElementId, roundMm } from "@/lib/reportLayout";
import type { LayoutElement, PageDesign } from "@/lib/reportLayout";
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
/** How many past states Ctrl+Z can step back through, per editor session. */
const MAX_HISTORY = 50;

// A single, module-level clipboard: Page Designer and Report Configuration
// are two separate LayoutEditor mounts (only one visible at a time — see
// TemplateBuilder), so this is what lets you copy an element on one page (or
// even the master) and paste it onto another without losing it on unmount.
let elementClipboard: LayoutElement | null = null;

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
  /** This page's real, rasterized PDF page (see useReportPageImages) — shown
   * as the canvas background so it reads as the actual final page. Elements
   * already present when this mount happened are drawn as invisible hit-
   * boxes over it (see bornIds below); only newly-added ones still show the
   * abstract preview, since they have no corresponding real pixels yet. */
  backgroundImage?: string | null;
}

export function LayoutEditor({
  design, elements, onElementsChange, leftHeader, masterElements, emptyHint, repeating = false, liveData,
  pinnedItem, backgroundImage, reportId,
}: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  // Margin/header/footer guides help while laying out a template, but on a
  // report (liveData present) they're just chrome between you and seeing
  // the page as its final, real self — off by default there, still
  // available via the checkbox for a moment of precise alignment.
  const [showGuides, setShowGuides] = useState(!liveData);
  const scale = BASE_SCALE * zoom;

  // Snapshot of which element ids already existed when this page (or edit
  // mode — see ReportConfigurator's key) was first shown. With a real
  // background image, those are already baked into it pixel-for-pixel —
  // rendering their abstract preview too would duplicate them visibly.
  // Never recomputed after mount, so an element added this session keeps
  // showing its preview (nothing real to show yet) even once selected/moved.
  const [bornIds] = useState<Set<string>>(() => new Set(elements.map((e) => e.id)));

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
    onCommit: (el) => commit((prev) => prev.map((e) => (e.id === el.id ? el : e))),
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
    setSelectedId(id);
  }

  function updateElement(next: LayoutElement) {
    commit((prev) =>
      prev.map((e) => (e.id === next.id ? clampToPage(next, design) : e)),
    );
  }

  function pasteElement() {
    if (!elementClipboard) return;
    const copyId = newElementId();
    const source = elementClipboard;
    commit((prev) => [
      ...prev,
      clampToPage(
        { ...source, id: copyId, x: source.x + 5, y: source.y + 5, z: topZ(prev) + 1, props: { ...source.props } },
        design,
      ),
    ]);
    setSelectedId(copyId);
  }

  function runAction(action: ElementAction, id: string) {
    if (action === "delete") {
      commit((prev) => prev.filter((e) => e.id !== id));
      setSelectedId(null);
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
      setSelectedId(copyId);
      return;
    }
    // Re-order: nudge z past the neighbour in that direction.
    const delta = action === "forward" ? 1 : -1;
    commit((prev) =>
      prev.map((e) => (e.id === id ? { ...e, z: Math.max(0, e.z + delta) } : e)),
    );
  }

  // Keyboard shortcuts: Delete/Backspace, Ctrl/Cmd+C/V, Ctrl/Cmd+Z (+Shift for redo).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return;
      const mod = event.ctrlKey || event.metaKey;

      if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
        event.preventDefault();
        runAction("delete", selectedId);
        return;
      }
      if (mod && event.key.toLowerCase() === "c" && selectedId) {
        const el = elementsRef.current.find((e) => e.id === selectedId);
        if (el) elementClipboard = { ...el, props: { ...el.props } };
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
  }, [selectedId, design, elements, onElementsChange]);

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
            alignGuides={guides}
            onSelect={setSelectedId}
            onStartMove={startMove}
            onStartResize={startResize}
            onStartRotate={startRotate}
            onAction={runAction}
            onDropSpec={(key, x, y) => addSpec(key, x, y)}
            liveData={liveData}
            pinnedItem={pinnedItem}
            backgroundImage={backgroundImage}
            bornIds={bornIds}
          />
        </div>

        {elements.length === 0 && emptyHint && (
          <p className={styles.emptyHint}>{emptyHint}</p>
        )}
      </main>

      <ElementInspector el={selected} onChange={updateElement} repeating={repeating} reportId={reportId} />
    </div>
  );
}
