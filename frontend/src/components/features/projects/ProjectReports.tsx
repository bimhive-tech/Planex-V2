"use client";

// Reports tab — a per-project hub for that project's generated reports:
// view/download each PDF, open the builder, or create a new one (locked to
// this project). Reuses the Reports feature's card + create drawer.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { API_BASE } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import { ReportCard } from "@/components/features/reports/ReportCard";
import { ReportFormDrawer } from "@/components/features/reports/ReportFormDrawer";
import { ProjectReportAssets } from "./ProjectReportAssets";
import type { ReportRow } from "@/types/report";
import styles from "@/components/features/reports/reports.module.css";

export function ProjectReports({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const [page, setPage] = useState(1);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<ReportRow>>(`/reports/?project=${projectId}&page=${page}`),
    [projectId, page],
  );
  const rows = data?.results ?? [];

  // Same-origin so the httpOnly auth cookie rides along; opens inline in a tab.
  function viewPdf(r: ReportRow) {
    window.open(`${API_BASE}/reports/${r.id}/pdf/`, "_blank", "noopener");
  }

  async function handleDelete(r: ReportRow) {
    if (!window.confirm(`Delete “${r.title}”? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/reports/${r.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete report.");
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.headRow}>
        <div>
          <h2 className={styles.title}>Reports</h2>
          <p className={styles.subtitle}>
            {data ? `${data.count} ${data.count === 1 ? "report" : "reports"} for this project` : "This project's reports"}
          </p>
        </div>
        {canManage && (
          <Button leadingIcon={<Icon name="plus" size={16} />} onClick={() => setDrawerOpen(true)}>New report</Button>
        )}
      </div>

      {/* Project-level report branding (logos, cover, site photos) used by every PDF. */}
      <ProjectReportAssets projectId={projectId} canManage={canManage} />

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={rows.length === 0}
        emptyTitle="No reports for this project yet"
        emptyText={canManage ? "Create a report to generate its PDF." : "Nothing to show here yet."}
        onRetry={reload}
      >
        <div className={styles.grid}>
          {rows.map((r) => (
            <ReportCard key={r.id} report={r} canManage={canManage} onView={viewPdf} onDelete={handleDelete} />
          ))}
        </div>
      </StateView>

      {data && (data.next || data.previous) && (
        <div className={styles.pagination}>
          <span>Page {page}</span>
          <div className={styles.pageBtns}>
            <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      <ReportFormDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} lockedProjectId={projectId} />
    </div>
  );
}
