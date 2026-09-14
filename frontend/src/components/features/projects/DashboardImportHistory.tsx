"use client";

// What dashboard workbooks have been imported into this project before — file,
// when, and who uploaded it (register item D2). The schedule tab has always
// shown its import history; the dashboard upload left no trace, so nobody
// could answer "where did these invoice figures come from?" without asking
// whoever uploaded them.
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api } from "@/lib/api";
import { API_BASE } from "@/lib/constants";
import { panelParts } from "@/lib/dashboardImport";
import { useFetch } from "@/hooks/useFetch";
import { formatDateTime } from "@/lib/format";
import type { DashboardImportRow } from "@/types/project";
import styles from "./finances.module.css";

/** What one upload brought in, from the importer's own reported result. Read
 * defensively: the shape is whatever that import recorded at the time, and an
 * older row may predate a part that exists now. */
function broughtIn(summary: DashboardImportRow["summary"]): string {
  const imported = summary?.imported ?? {};
  const parts: string[] = [];
  if (imported.cashflow) {
    parts.push(`${imported.cashflow.months} months of cash flow`);
    if (imported.cashflow.curve_months) parts.push(`${imported.cashflow.curve_months} curve points`);
  }
  if (imported.invoices) {
    const i = imported.invoices;
    parts.push(`${i.periods} invoice${i.periods === 1 ? "" : "s"}`);
  }
  parts.push(...panelParts(imported.panels));
  return parts.length ? parts.join(", ") : "nothing recorded";
}

export function DashboardImportHistory({ projectId, reloadKey }: {
  projectId: string;
  /** Bumped by the importer above so a fresh upload appears without a refresh. */
  reloadKey: number;
}) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<DashboardImportRow[]>(`/projects/${projectId}/dashboard/imports/`),
    [projectId, reloadKey],
  );
  const rows = data ?? [];

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Import history</h2>
      </header>
      <StateView
        loading={loading} error={error} isEmpty={rows.length === 0}
        emptyTitle="Nothing imported yet"
        emptyText="Dashboard workbooks you import appear here, with who uploaded them."
        onRetry={reload}
      >
        <div className={styles.tableWrap}>
          <table className={styles.grid}>
            <thead>
              <tr><th>File</th><th>Imported</th><th>By</th><th>Brought in</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    {r.file_url
                      ? (
                        <a className={styles.fileLink} href={`${API_BASE}${r.file_url.replace(/^\/api/, "")}`}>
                          <Icon name="download" size={14} />
                          {r.source || "workbook.xlsx"}
                        </a>
                      )
                      : (r.source || "—")}
                  </td>
                  <td>{formatDateTime(r.created_at)}</td>
                  {/* Blank for an upload whose user has since been deleted. */}
                  <td>{r.uploaded_by_name || "—"}</td>
                  <td className={styles.muted}>{broughtIn(r.summary)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </StateView>
    </section>
  );
}
