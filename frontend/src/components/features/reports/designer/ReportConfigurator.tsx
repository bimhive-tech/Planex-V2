"use client";

// Tab 2 — Report Configuration. The Canva-style surface: a page list on the
// left, drag/drop/resize on the paper, and the master page showing through as
// a ghost so you can see what's already reserved.
import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { newElementId } from "@/lib/reportLayout";
import type { LayoutElement, LayoutPage, PageDesign } from "@/lib/reportLayout";
import { LayoutEditor } from "./LayoutEditor";
import styles from "./designer.module.css";

interface Props {
  design: PageDesign;
  pages: LayoutPage[];
  /** Updater form so rapid successive edits can't clobber each other. */
  onChange: (updater: (prev: LayoutPage[]) => LayoutPage[]) => void;
}

export function ReportConfigurator({ design, pages, onChange }: Props) {
  const [activeId, setActiveId] = useState<string>(pages[0]?.id ?? "");
  const [renamingId, setRenamingId] = useState<string | null>(null);

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

  const pageList = (
    <section className={styles.setupPanel} aria-label="Report pages">
      <div className={styles.pagesHead}>
        <h2 className={styles.panelTitle}>Pages</h2>
        <button type="button" className={styles.addPageBtn} onClick={addPage}>
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
              <button type="button" onClick={() => movePage(page.id, -1)} aria-label="Move up" disabled={index === 0}>
                <Icon name="chevronDown" size={12} className={styles.flipUp} />
              </button>
              <button
                type="button" onClick={() => movePage(page.id, 1)} aria-label="Move down"
                disabled={index === pages.length - 1}
              >
                <Icon name="chevronDown" size={12} />
              </button>
              <button type="button" onClick={() => duplicatePage(page.id)} aria-label="Duplicate page">
                <Icon name="copy" size={12} />
              </button>
              <button
                type="button" onClick={() => deletePage(page.id)} aria-label="Delete page"
                disabled={pages.length === 1} className={styles.pageDelete}
              >
                <Icon name="trash" size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>
      <p className={styles.panelHint}>Double-click a page name to rename it.</p>
    </section>
  );

  return (
    <LayoutEditor
      key={active.id}
      design={design}
      elements={active.elements}
      onElementsChange={setElements}
      masterElements={design.master_elements}
      leftHeader={pageList}
      emptyHint="Drag an element from the left onto the page to start building this page."
    />
  );
}
