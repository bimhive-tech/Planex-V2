"use client";

// Reports Hub: every generated report in the company, with create/edit and
// on-demand PDF view/download. Templates live on a sibling tab.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { API_BASE, ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import type { ReportRow } from "@/types/report";
import { ReportCard } from "./ReportCard";
import { ReportFormDrawer } from "./ReportFormDrawer";
import styles from "./reports.module.css";

export function ReportsHub({ canManage }: { canManage: boolean }) {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<ReportRow>>(`/reports/?page=${page}`),
    [page],
  );
  const rows = data?.results ?? [];

  // Same-origin so the httpOnly auth cookie rides along; opens inline in a tab.
  function viewPdf(r: ReportRow) {
    window.open(`${API_BASE}/reports/${r.id}/pdf/`, "_blank", "noopener");
  }

  /** Start next month from last month's report — copies the whole setup
   * including its customised layout, so the pages/tables/edits don't have to
   * be rebuilt by hand every cycle. Dates and photos deliberately don't carry
   * over (see the backend's `duplicate` action). */
  async function handleDuplicate(r: ReportRow) {
    setActionError(null);
    try {
      const copy = await api.post<ReportRow>(`/reports/${r.id}/duplicate/`, {
        title: `${r.title} (copy)`,
      });
      reload();
      // Straight into the copy — the next thing you do is set its period.
      router.push(ROUTES.report(copy.id));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't duplicate report.");
    }
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
      <header className={styles.head}>
        <div className={styles.headRow}>
          <div>
            <h1 className={styles.title}>Reports</h1>
            <p className={styles.subtitle}>
              {data ? `${data.count} ${data.count === 1 ? "report" : "reports"}` : "Generated project reports"}
            </p>
          </div>
          {canManage && (
            <Button leadingIcon={<Icon name="plus" size={16} />} onClick={() => setDrawerOpen(true)}>New report</Button>
          )}
        </div>
        <nav className={styles.tabs}>
          <span className={`${styles.tab} ${styles.tabActive}`}>Reports</span>
          {canManage && <Link href={ROUTES.reportTemplates} className={styles.tab}>Templates</Link>}
        </nav>
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={rows.length === 0}
        emptyTitle="No reports yet"
        emptyText={canManage ? "Create your first report to generate a PDF." : "Nothing to show here yet."}
        onRetry={reload}
      >
        <div className={styles.grid}>
          {rows.map((r) => (
            <ReportCard
              key={r.id}
              report={r}
              canManage={canManage}
              onView={viewPdf}
              onDuplicate={handleDuplicate}
              onDelete={handleDelete}
            />
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

      <ReportFormDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
