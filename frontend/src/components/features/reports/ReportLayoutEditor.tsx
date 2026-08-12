"use client";

// Report Builder's "Customize" tab — this one report's own pages, layered on
// top of its template (add a page, drop an extra photo somewhere the
// template doesn't have one, move the header logo) without ever touching the
// template. Reuses the exact page-list + canvas + palette + inspector from
// the Template Builder's Report Configuration tab, bound to this report's
// layout_override instead of a template's config. Margins/page size stay
// template-controlled; page content AND the header/footer master content are
// both editable here.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { StateView } from "@/components/ui/StateView";
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
  /** True until the very first `liveData` fetch settles (success or
   * failure) — see the `everSettled` gate below. Without this, the canvas
   * could unlock as soon as the page-image render finished even though
   * liveData was still null, showing every table/chart's generic
   * placeholder and looking like real data had silently failed to load. */
  liveDataLoading: boolean;
  canManage: boolean;
  /** Refreshes the report row + the PDF preview after a save/reset. */
  onSaved: () => void;
}

export function ReportLayoutEditor({
  reportId, template, savedOverride, liveData, liveDataLoading, canManage, onSaved,
}: Props) {
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
  const [pageNumberMap, setPageNumberMap] = useState<Map<string, number>>(() => {
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
  // "Refresh preview" (manual, not automatic — a render of this size can
  // take 30-90s, too slow to fire on every pause in editing) renders the
  // CURRENT unsaved draft and swaps these in ahead of the saved pageImages
  // above. Cleared on the next real save/reset, since that regenerates the
  // saved images anyway and should take back over.
  const [previewImages, setPreviewImages] = useState<string[] | null>(null);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  useEffect(() => { setPreviewImages(null); }, [imagesKey]);
  const effectiveImages = previewImages ?? pageImages;
  // Blocks the canvas until BOTH the real page backgrounds AND the live
  // project data have loaded once — either one finishing alone used to be
  // enough to unlock editing, so a report whose /data/ fetch was slower
  // than its page-image render (its own separate ~7s+ query, see
  // ReportDetail) would show every table/chart's generic placeholder
  // content instead of the real thing, looking like real data had
  // silently failed to load. Stays true for the rest of the session once
  // both first settle, so a later re-generate-after-save doesn't lock the
  // whole editor again.
  const [everSettled, setEverSettled] = useState(false);
  useEffect(() => {
    if (!imagesLoading && !liveDataLoading) setEverSettled(true);
  }, [imagesLoading, liveDataLoading]);

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

  // Renders the current unsaved draft into real page backgrounds without
  // persisting anything — lets newly added/edited elements show their real
  // rendered look ahead of a full Save. Manual (not automatic on a pause in
  // editing): a report this size can take 30-90s to render, which would
  // make auto-refresh feel like the editor had frozen.
  async function refreshPreview() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const res = await fetch(`/reports/${reportId}/preview-images-file`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout_override: { layout: { pages }, page_design: { master_elements: masterElements } },
        }),
      });
      if (!res.ok) throw new Error("preview refresh failed");
      const data: { pages: string[] } = await res.json();
      setPreviewImages(data.pages.map((b64) => `data:image/png;base64,${b64}`));
      // The response's pages are exactly `pages` in order — recompute the
      // number map from that so a page added this session (no entry yet in
      // the original map) also gets a real background from here on.
      setPageNumberMap(new Map(pages.map((p, i) => [p.id, i + 1])));
      setPreviewVersion((v) => v + 1);
    } catch {
      setRefreshError("Couldn't refresh the preview — try again.");
    } finally {
      setRefreshing(false);
    }
  }

  if (!template || !design) {
    return (
      <section className={styles.tabPanel}>
        <p className={styles.hint}>Pick a template on the Setup tab first — this report's custom pages start as a copy of the template&apos;s.</p>
      </section>
    );
  }

  // Block the editor until the report's real pages have rendered once —
  // dragging elements onto a canvas whose background hasn't loaded yet
  // meant working blind against the wrong (or a missing) page image.
  if (!everSettled) {
    return (
      <section className={styles.tabPanel}>
        <StateView loading error={null} isEmpty={false}>{null}</StateView>
        <p className={styles.hint}>Loading this report's real pages so you can start customizing…</p>
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
            <Button variant="secondary" onClick={refreshPreview} disabled={refreshing || saving}>
              {refreshing ? "Refreshing preview…" : "Refresh preview"}
            </Button>
            <Button onClick={save} disabled={saving || !dirty}>
              {saving ? "Saving…" : "Save custom layout"}
            </Button>
          </div>
        )}
      </div>
      {error && <p className="formError">{error}</p>}
      {refreshError && <p className="formError">{refreshError}</p>}
      <div className={styles.canvasWrap}>
        {refreshing && (
          <div className={styles.refreshOverlay} role="status" aria-live="polite">
            <span className={styles.refreshSpinner} aria-hidden="true" />
            <p className={styles.refreshOverlayText}>
              Refreshing the real preview — re-rendering every page, this can take a bit on a large report…
            </p>
          </div>
        )}
        <ReportConfigurator
          design={design}
          pages={pages}
          onChange={updatePages}
          liveData={liveData}
          reportId={reportId}
          masterElements={masterElements}
          onMasterElementsChange={updateMasterElements}
          pageImages={effectiveImages}
          pageImagesLoading={imagesLoading}
          pageNumberMap={pageNumberMap}
          previewVersion={previewVersion}
        />
      </div>
    </section>
  );
}
