"use client";

// Tab 2 — Report Configuration. The Canva-style surface: a page list on the
// left, drag/drop/resize on the paper, and the master page showing through as
// a ghost so you can see what's already reserved.
import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { newElementId, REPEAT_SOURCES } from "@/lib/reportLayout";
import type {
  ChartSvgMap, LayoutElement, LayoutPage, PageDesign, PageRepeat, RepeatSource, TableDataMap, TocEntry,
} from "@/lib/reportLayout";
import { resolvePinnedItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { LayoutEditor } from "./LayoutEditor";
import { PageStrip } from "./PageStrip";
import styles from "./designer.module.css";

const DEFAULT_REPEAT: PageRepeat = { source: "photos", mode: "chunk", chunk_size: 4 };

interface Props {
  design: PageDesign;
  pages: LayoutPage[];
  /** Updater form so rapid successive edits can't clobber each other. */
  onChange: (updater: (prev: LayoutPage[]) => LayoutPage[]) => void;
  /** Present only in the report-level "Customize" tab — undefined in the
   * project-agnostic Template Builder, where placeholders are all there is. */
  liveData?: ReportData | null;
  /** This report's id — present only alongside liveData. Passed through to
   * the inspector's image-upload control. */
  reportId?: string;
  /** This report's own header/footer content — present only alongside
   * liveData. Undefined in the Template Builder, where the master is edited
   * on its own dedicated Page Designer tab instead. */
  masterElements?: LayoutElement[];
  onMasterElementsChange?: (updater: (prev: LayoutElement[]) => LayoutElement[]) => void;
  /** Live, real per-chart previews — see useChartSvgs. Present only
   * alongside liveData; undefined in the Template Builder. */
  chartSvgs?: ChartSvgMap;
  /** Live, real per-table data — each table's own effective style (colors,
   * font size, padding) travels with it — see useTableData. */
  tableData?: TableDataMap;
  /** False until chartSvgs/tableData's first real response has landed —
   * chart/table boxes grey out instead of showing the generic mockup.
   * Defaults true (Template Builder — chartSvgs/tableData never load at
   * all there, so the mockup is the only look and always "ready"). */
  previewsReady?: boolean;
}

export function ReportConfigurator({
  design, pages, onChange, liveData, reportId, masterElements, onMasterElementsChange,
  chartSvgs, tableData, previewsReady = true,
}: Props) {
  // Every page's real name + real page number, for any "toc" element on the
  // canvas — mirrors apps/reports/pdf_canvas.py's build_canvas_pdf toc_map/
  // toc_order exactly (1-based position in this exact page sequence).
  // Needs only the page list, so it's available in both the report
  // Customize tab and the project-agnostic Template Builder.
  const tocEntries: TocEntry[] = pages.map((p, i) => ({ id: p.id, name: p.name, number: i + 1 }));

  const [activeId, setActiveId] = useState<string>(pages[0]?.id ?? "");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  // Whether you're moving this page's own content around, or the shared
  // header/footer (only offered where onMasterElementsChange exists — the
  // report Customize tab; the Template Builder edits the master on its own
  // separate Page Designer tab instead).
  const [editMode, setEditMode] = useState<"page" | "header">("page");
  // Repeat/skip-master are template-authoring concepts — a report's pages
  // are already real, concrete pages (see expandRepeatingPages), so those
  // controls are just noise here. Template Builder (no liveData) keeps them.
  const isReportContext = Boolean(liveData);

  const active = pages.find((p) => p.id === activeId) ?? pages[0];

  function setElements(updater: (prev: LayoutElement[]) => LayoutElement[]) {
    onChange((prev) =>
      prev.map((p) => (p.id === active.id ? { ...p, elements: updater(p.elements) } : p)),
    );
  }

  function addPage() {
    const id = newElementId();
    onChange((prev) => [...prev, { id, name: `Page ${prev.length + 1}`, elements: [] }]);
    setActiveId(id);
  }

  function duplicatePage(id: string) {
    const copyId = newElementId();
    onChange((prev) => {
      const index = prev.findIndex((p) => p.id === id);
      if (index < 0) return prev;
      const source = prev[index];
      const copy: LayoutPage = {
        id: copyId,
        name: `${source.name} copy`,
        // New ids for the copied elements, or selection would hit two of them.
        elements: source.elements.map((e) => ({ ...e, id: newElementId(), props: { ...e.props } })),
      };
      return [...prev.slice(0, index + 1), copy, ...prev.slice(index + 1)];
    });
    setActiveId(copyId);
  }

  function deletePage(id: string) {
    if (pages.length === 1) return; // a report always has at least one page
    onChange((prev) => (prev.length === 1 ? prev : prev.filter((p) => p.id !== id)));
    if (activeId === id) setActiveId(pages.find((p) => p.id !== id)!.id);
  }

  function movePage(id: string, delta: -1 | 1) {
    onChange((prev) => {
      const index = prev.findIndex((p) => p.id === id);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function toggleRepeat(id: string) {
    onChange((prev) => prev.map((p) => {
      if (p.id !== id) return p;
      if (!p.repeat) return { ...p, repeat: DEFAULT_REPEAT };
      const next = { ...p };
      delete next.repeat;
      return next;
    }));
  }

  function setRepeat(id: string, patch: Partial<PageRepeat>) {
    onChange((prev) => prev.map((p) => {
      if (p.id !== id || !p.repeat) return p;
      // A pinned (expanded) page's pin_index refers to a position in the OLD
      // source/mode's item list — changing either invalidates it.
      const clearsPin = "source" in patch || "mode" in patch;
      const nextRepeat = { ...p.repeat, ...patch };
      if (clearsPin) delete nextRepeat.pin_index;
      return { ...p, repeat: nextRepeat };
    }));
  }

  function toggleSkipMaster(id: string) {
    onChange((prev) => prev.map((p) => (p.id === id ? { ...p, skip_master: !p.skip_master } : p)));
  }

  const pageList = (
    <section className={styles.setupPanel} aria-label="Report pages">
      {onMasterElementsChange && (
        <div className={styles.editModeTabs} role="tablist" aria-label="What to edit">
          <button
            type="button" role="tab" aria-selected={editMode === "page"}
            className={editMode === "page" ? styles.editModeTabActive : styles.editModeTab}
            onClick={() => setEditMode("page")}
          >
            Page content
          </button>
          <button
            type="button" role="tab" aria-selected={editMode === "header"}
            className={editMode === "header" ? styles.editModeTabActive : styles.editModeTab}
            onClick={() => setEditMode("header")}
          >
            Header &amp; footer
          </button>
        </div>
      )}

      <div className={styles.pagesHead}>
        <h2 className={styles.panelTitle}>Pages</h2>
        <button type="button" className={styles.addPageBtn} onClick={addPage} title="Add a new page">
          <Icon name="plus" size={14} /> Add
        </button>
      </div>

      <div className={styles.pageList}>
        {pages.map((page, index) => (
          <div
            key={page.id}
            className={`${styles.pageRow} ${page.id === active.id ? styles.pageRowActive : ""}`}
          >
            <button
              type="button"
              className={styles.pageRowMain}
              onClick={() => setActiveId(page.id)}
              onDoubleClick={() => setRenamingId(page.id)}
            >
              <span className={styles.pageIndex}>{index + 1}</span>
              {!isReportContext && page.repeat && <Icon name="refresh" size={12} className={styles.repeatBadge} />}
              {!isReportContext && page.skip_master && <Icon name="eyeOff" size={12} className={styles.repeatBadge} />}
              {renamingId === page.id ? (
                <input
                  className={styles.pageNameInput}
                  value={page.name}
                  autoFocus
                  onChange={(e) =>
                    onChange((prev) =>
                      prev.map((p) => (p.id === page.id ? { ...p, name: e.target.value } : p)))
                  }
                  onBlur={() => setRenamingId(null)}
                  onKeyDown={(e) => e.key === "Enter" && setRenamingId(null)}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className={styles.pageName}>{page.name}</span>
              )}
              <span className={styles.pageCount}>{page.elements.length}</span>
            </button>

            <div className={styles.pageActions}>
              <button
                type="button" onClick={() => movePage(page.id, -1)}
                aria-label="Move up" title="Move up" disabled={index === 0}
              >
                <Icon name="chevronDown" size={12} className={styles.flipUp} />
              </button>
              <button
                type="button" onClick={() => movePage(page.id, 1)}
                aria-label="Move down" title="Move down"
                disabled={index === pages.length - 1}
              >
                <Icon name="chevronDown" size={12} />
              </button>
              {!isReportContext && (
                <button
                  type="button" onClick={() => toggleRepeat(page.id)}
                  aria-label="Repeat this page per item" title="Repeat this page per item (photos, zones, etc.)"
                  className={page.repeat ? styles.repeatActive : undefined}
                >
                  <Icon name="refresh" size={12} />
                </button>
              )}
              {!isReportContext && (
                <button
                  type="button" onClick={() => toggleSkipMaster(page.id)}
                  aria-label="Hide the repeating header/footer on this page"
                  title="Hide the repeating header/footer on this page (e.g. for a cover)"
                  className={page.skip_master ? styles.repeatActive : undefined}
                >
                  <Icon name="eyeOff" size={12} />
                </button>
              )}
              <button
                type="button" onClick={() => duplicatePage(page.id)}
                aria-label="Duplicate page" title="Duplicate this page"
              >
                <Icon name="copy" size={12} />
              </button>
              <button
                type="button" onClick={() => deletePage(page.id)}
                aria-label="Delete page" title="Delete this page"
                disabled={pages.length === 1} className={styles.pageDelete}
              >
                <Icon name="trash" size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>
      <p className={styles.panelHint}>Double-click a page name to rename it.</p>

      {!isReportContext && active.repeat && (
        <div className={styles.repeatPanel}>
          <h3 className={styles.repeatPanelTitle}>Repeat this page</h3>
          <p className={styles.panelHint}>
            One page becomes many — cloned once per {active.repeat.mode === "chunk" ? "chunk of" : ""} item below.
          </p>
          <label className={styles.propField}>
            <span>Source</span>
            <select
              value={active.repeat.source}
              onChange={(e) => setRepeat(active.id, { source: e.target.value as RepeatSource })}
            >
              {REPEAT_SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </label>
          <label className={styles.propField}>
            <span>Mode</span>
            <select
              value={active.repeat.mode}
              onChange={(e) => setRepeat(active.id, { mode: e.target.value as "one_per_item" | "chunk" })}
            >
              <option value="one_per_item">One page per item</option>
              <option value="chunk">Group N items per page</option>
            </select>
          </label>
          {active.repeat.mode === "chunk" && (
            <label className={styles.propField}>
              <span>Items per page</span>
              <input
                type="number" min={1} value={active.repeat.chunk_size ?? 4}
                onChange={(e) => setRepeat(active.id, { chunk_size: Number(e.target.value) })}
              />
            </label>
          )}
        </div>
      )}
    </section>
  );

  const pinnedItem = liveData ? resolvePinnedItem(active, liveData) : null;
  const editingHeader = editMode === "header" && Boolean(onMasterElementsChange);

  return (
    <LayoutEditor
      // Mode is part of the key (not just the page) — switching between
      // "Page content" and "Header & footer" is a different editable set
      // entirely, so it should get its own fresh undo history rather than
      // inheriting the page's.
      key={`${active.id}-${editMode}`}
      design={design}
      elements={editingHeader ? (masterElements ?? []) : active.elements}
      onElementsChange={editingHeader ? onMasterElementsChange! : setElements}
      masterElements={editingHeader || active.skip_master ? [] : (masterElements ?? design.master_elements)}
      leftHeader={pageList}
      emptyHint={
        editingHeader
          ? "Drag an element from the left to add to the header/footer."
          : "Drag an element from the left onto the page to start building this page."
      }
      repeating={Boolean(active.repeat)}
      liveData={liveData}
      reportId={reportId}
      pinnedItem={editingHeader ? null : pinnedItem}
      chartSvgs={chartSvgs}
      tableData={tableData}
      previewsReady={previewsReady}
      tocEntries={tocEntries}
      ownPageId={active.id}
      bottomPanel={
        editingHeader ? undefined : (
          <PageStrip
            pages={pages}
            design={design}
            activeId={active.id}
            onSelect={setActiveId}
            onDuplicate={duplicatePage}
            onDelete={deletePage}
            onAdd={addPage}
          />
        )
      }
    />
  );
}
