"use client";

// Report Builder's "Customize" tab — this one report's own pages, layered on
// top of its template (add a page, drop an extra photo somewhere the
// template doesn't have one, move the header logo) without ever touching the
// template. Reuses the exact page-list + canvas + palette + inspector from
// the Template Builder's Report Configuration tab, bound to this report's
// layout_override instead of a template's config. Margins/page size stay
// template-controlled; page content AND the header/footer master content are
// both editable here.
//
// Every element renders live from real project data (see ElementPreview) —
// tables and charts specifically render the exact same output the real PDF
// does (useTableData/useChartSvgs), not an approximation and not a static
// full-page snapshot. There's nothing to "refresh": moving or editing an
// element updates its own live preview directly, the same way every other
// element type already did.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { useChartSvgs } from "@/hooks/useChartSvgs";
import { useTableData } from "@/hooks/useTableData";
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
   * failure) — see the `everSettled` gate below. Without it the canvas
   * could unlock before liveData arrived, showing every table/chart's
   * generic placeholder and looking like real data had silently failed. */
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
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Resetting discards every custom page/text edit this report has of its
  // own (including any table/TOC/field overrides — see ElementPreview's
  // InlineEditableText) with no undo once saved, so it's gated behind an
  // explicit confirmation rather than firing on the first click.
  const [confirmingReset, setConfirmingReset] = useState(false);
  // Live, real chart/table previews — see each hook's own doc comment.
  // Debounced and cheap (no PDF assembly, no full-page rasterization), so
  // every edit updates them directly instead of waiting on an explicit
  // refresh or a save.
  const { charts: chartSvgs, loaded: chartsLoaded } = useChartSvgs(reportId, pages, masterElements);
  const { tables: tableData, loaded: tablesLoaded } = useTableData(reportId, pages, masterElements);
  // Neither hook has produced its first real response yet — chart/table
  // boxes grey out instead of showing the generic client-side mockup, so a
  // still-loading canvas never looks like it's already showing real content.
  const previewsReady = chartsLoaded && tablesLoaded;

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
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this report's layout.");
    } finally {
      setSaving(false);
    }
  }

  async function resetToTemplate() {
    setConfirmingReset(false);
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/reports/${reportId}/`, { layout_override: null });
      setPages(startingPages);
      setMasterElements(design?.master_elements ?? []);
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

  // Block the editor until the report's live project data has loaded once —
  // editing against generic placeholder content is confusing and every
  // element needs liveData to show its real look.
  if (liveDataLoading) {
    return (
      <section className={styles.tabPanel}>
        <StateView loading error={null} isEmpty={false}>{null}</StateView>
        <p className={styles.hint}>Loading this report's real data so you can start customizing…</p>
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
              <Button variant="secondary" onClick={() => setConfirmingReset(true)} disabled={saving}>
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
        reportId={reportId}
        masterElements={masterElements}
        onMasterElementsChange={updateMasterElements}
        chartSvgs={chartSvgs}
        tableData={tableData}
        previewsReady={previewsReady}
      />
      <Modal
        open={confirmingReset}
        title="Reset to template?"
        onClose={() => setConfirmingReset(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmingReset(false)}>Cancel</Button>
            <Button onClick={resetToTemplate} disabled={saving}>
              {saving ? "Resetting…" : "Reset to template"}
            </Button>
          </>
        }
      >
        <p>
          This discards every page, text edit, and table/field/TOC override this report has of its own — including
          anything not yet saved — and goes back to exactly what the template says. This can&apos;t be undone.
        </p>
      </Modal>
    </section>
  );
}
