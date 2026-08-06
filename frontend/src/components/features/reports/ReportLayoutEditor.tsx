"use client";

// Report Builder's "Customize" tab — this one report's own pages, layered on
// top of its template (add a page, drop an extra photo somewhere the
// template doesn't have one) without ever touching the template. Reuses the
// exact page-list + canvas + palette + inspector from the Template Builder's
// Report Configuration tab, bound to this report's layout_override instead
// of a template's config. Page setup (margins, master header/footer) stays
// template-controlled — only page content is editable here.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import { readPageDesign, readPages } from "@/lib/reportLayout";
import type { LayoutPage } from "@/lib/reportLayout";
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
  /** The already-rendered PDF (same one PdfViewer shows) — used as the real
   * page image behind each page's editable boxes, like an "edit PDF" tool. */
  pdfUrl: string;
  canManage: boolean;
  /** Refreshes the report row + the PDF preview after a save/reset. */
  onSaved: () => void;
}

export function ReportLayoutEditor({ reportId, template, savedOverride, liveData, pdfUrl, canManage, onSaved }: Props) {
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
  // A snapshot of "page id -> real PDF page number", taken once from the
  // starting pages (which match pdfUrl's current render 1:1 — the PDF was
  // rendered from this same template/override). Deliberately never
  // recomputed as you add/delete/reorder pages during the session: each
  // page keeps showing the real page it started as, and a brand-new page has
  // no entry (no background image) until the next save regenerates pdfUrl.
  const [pageNumberMap] = useState<Map<string, number>>(() => {
    const base = isCustomized ? savedOverride!.layout!.pages : startingPages;
    return new Map(base.map((p, i) => [p.id, i + 1]));
  });
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updatePages(updater: (prev: LayoutPage[]) => LayoutPage[]) {
    setPages(updater);
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/reports/${reportId}/`, { layout_override: { layout: { pages } } });
      setDirty(false);
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
      setDirty(false);
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
      <ReportConfigurator design={design} pages={pages} onChange={updatePages} liveData={liveData}
        pdfUrl={pdfUrl} pageNumberMap={pageNumberMap} />
    </section>
  );
}
