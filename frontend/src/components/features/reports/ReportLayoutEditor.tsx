"use client";

// Report Builder's "Customize" tab — this one report's own pages, layered on
// top of its template (add a page, drop an extra photo somewhere the
// template doesn't have one, move the header logo) without ever touching the
// template. Reuses the exact page-list + canvas + palette + inspector from
// the Template Builder's Report Configuration tab, bound to this report's
// layout_override instead of a template's config. Margins/page size stay
// template-controlled; page content AND the header/footer master content are
// both editable here.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { useReportPageImages } from "@/hooks/useReportPageImages";
import { api, ApiError } from "@/lib/api";
import { readPageDesign, readPages } from "@/lib/reportLayout";
import type { LayoutElement, LayoutPage } from "@/lib/reportLayout";
import { expandRepeatingPages } from "@/lib/reportRepeat";
import type { ReportData, ReportLayoutOverride, ReportTemplate } from "@/types/report";
import { ReportConfigurator } from "./designer/ReportConfigurator";
import styles from "./reports.module.css";

interface Props {
  reportId: string;
  template: ReportTemplate | null;
  savedOverride: ReportLayoutOverride | null;
  /** This report's live project data — shown inside table/chart/field
   * elements on the canvas instead of generic placeholder content. */
  liveData: ReportData | null;
  canManage: boolean;
  /** Refreshes the report row + the PDF preview after a save/reset. */
  onSaved: () => void;
}

export function ReportLayoutEditor({ reportId, template, savedOverride, liveData, canManage, onSaved }: Props) {
  const design = template ? readPageDesign(template.config) : null;
  const templatePages = template ? readPages(template.config) : [];
  // A repeating page (e.g. "one per zone") is one row in the template but N
  // real pages in the actual PDF — expand it into that many concrete,
  // individually-editable pages up front, so what you browse and edit here
  // already matches the real page count instead of the template's raw types.
  const startingPages = liveData ? expandRepeatingPages(templatePages, liveData) : templatePages;
  const isCustomized = Boolean(savedOverride?.layout?.pages?.length);

  // Keyed by reportId at the call site (see ReportDetail) so switching reports
  // remounts this with a fresh starting state instead of carrying over edits.
  const [pages, setPages] = useState<LayoutPage[]>(
    isCustomized ? savedOverride!.layout!.pages : startingPages,
  );
  const [masterElements, setMasterElements] = useState<LayoutElement[]>(
    savedOverride?.page_design?.master_elements ?? design?.master_elements ?? [],
  );
  // A snapshot of "page id -> its position in the real PDF" (1-based), taken
  // once from the starting pages — matches pageImages 1:1 since the PDF was
  // rendered from this exact template/override just before this tab opened.
  // Deliberately never recomputed as pages are added/reordered during the
  // session: each page keeps showing the real image it started with, and a
  // brand-new page has no entry until the next save regenerates the set.
  const [pageNumberMap] = useState<Map<string, number>>(() => {
    const base = isCustomized ? savedOverride!.layout!.pages : startingPages;
    return new Map(base.map((p, i) => [p.id, i + 1]));
  });
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumped only after a save/reset actually changes what the PDF looks like —
  // regenerating it (10-20s) on every keystroke would make editing unusable.
  const [imagesKey, setImagesKey] = useState(0);
  const { images: pageImages, loading: imagesLoading } = useReportPageImages(reportId, imagesKey);

  function updatePages(updater: (prev: LayoutPage[]) => LayoutPage[]) {
    setPages(updater);
    setDirty(true);
  }

  function updateMasterElements(updater: (prev: LayoutElement[]) => LayoutElement[]) {
    setMasterElements(updater);
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/reports/${reportId}/`, {
        layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
      });
      setDirty(false);
      setImagesKey((k) => k + 1);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this report's layout.");
    } finally {
      setSaving(false);
    }
  }

  async function resetToTemplate() {
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/reports/${reportId}/`, { layout_override: null });
      setPages(startingPages);
      setMasterElements(design?.master_elements ?? []);
      setDirty(false);
      setImagesKey((k) => k + 1);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reset this report's layout.");
    } finally {
      setSaving(false);
    }
  }

  if (!template || !design) {
    return (
      <section className={styles.tabPanel}>
        <p className={styles.hint}>Pick a template on the Setup tab first — this report's custom pages start as a copy of the template&apos;s.</p>
      </section>
    );
  }

  return (
    <section className={styles.tabPanel}>
      <div className={styles.fieldRow}>
        <p className={styles.hint}>
          {isCustomized
            ? "This report has its own pages, separate from the template — changes here only affect this report."
            : "Starts identical to the template. Saving gives this report its own pages, independent from the template from then on."}
        </p>
        {canManage && (
          <div className={styles.detailActions}>
            {isCustomized && (
              <Button variant="secondary" onClick={resetToTemplate} disabled={saving}>
                Reset to template
              </Button>
            )}
            <Button onClick={save} disabled={saving || !dirty}>
              {saving ? "Saving…" : "Save custom layout"}
            </Button>
          </div>
        )}
      </div>
      {error && <p className="formError">{error}</p>}
      <ReportConfigurator
        design={design}
        pages={pages}
        onChange={updatePages}
        liveData={liveData}
        masterElements={masterElements}
        onMasterElementsChange={updateMasterElements}
        pageImages={pageImages}
        pageImagesLoading={imagesLoading}
        pageNumberMap={pageNumberMap}
      />
    </section>
  );
}
