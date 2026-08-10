"use client";

// Full, paginated, per-activity breakdown of every cost/schedule column a P6
// import carries — the detailed list under the "Schedule Cost" sub-tab's totals.
import { useEffect, useState } from "react";

import { StateView } from "@/components/ui/StateView";
import { Button } from "@/components/ui/Button";
import { api, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import styles from "./finances.module.css";

interface ActivityScheduleRow {
  id: string;
  name: string;
  code: string;
  phase_name: string;
  budgeted_cost: string | null;
  earned_value_cost: string | null;
  schedule_variance: string | null;
  baseline_duration: number | null;
  original_duration: number | null;
  actual_duration: number | null;
  remaining_duration: number | null;
  schedule_performance_index: string | null;
  total_float: number | null;
}

function num(v: string | number | null, digits = 0): string {
  if (v === null) return "—";
  const n = Number(v);
  return Number.isNaN(n) ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function ActivityScheduleTable({ projectId }: { projectId: string }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<ActivityScheduleRow>>(
      `/projects/${projectId}/activity-schedule/?page=${page}${debounced ? `&search=${encodeURIComponent(debounced)}` : ""}`,
    ),
    [projectId, page, debounced],
  );
  const rows = data?.results ?? [];

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Activity Detail</h2>
        <span className={styles.muted}>{data ? `${data.count.toLocaleString()} activities` : ""}</span>
      </header>

      <input
        className={styles.search}
        type="search"
        placeholder="Search by name or code…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        aria-label="Search activities"
      />

      <StateView loading={loading} error={error} isEmpty={rows.length === 0}
        emptyTitle="No activities found" onRetry={reload}>
        <div className={styles.tableWrap}>
          <table className={styles.grid}>
            <thead>
              <tr>
                <th>Activity</th>
                <th>Budgeted Cost</th>
                <th>Earned Value</th>
                <th>Schedule Variance</th>
                <th>BL Duration</th>
                <th>Original Duration</th>
                <th>Actual Duration</th>
                <th>Remaining Duration</th>
                <th>SPI</th>
                <th>Total Float</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}{r.phase_name ? <span className={styles.muted}> · {r.phase_name}</span> : ""}</td>
                  <td className="tnum">{num(r.budgeted_cost)}</td>
                  <td className="tnum">{num(r.earned_value_cost)}</td>
                  <td className="tnum">{num(r.schedule_variance)}</td>
                  <td className="tnum">{num(r.baseline_duration)}</td>
                  <td className="tnum">{num(r.original_duration)}</td>
                  <td className="tnum">{num(r.actual_duration)}</td>
                  <td className="tnum">{num(r.remaining_duration)}</td>
                  <td className="tnum">{num(r.schedule_performance_index, 2)}</td>
                  <td className="tnum">{num(r.total_float)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data && (data.next || data.previous) && (
          <div className={styles.pagination}>
            <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className={styles.muted}>Page {page}</span>
            <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </StateView>
    </section>
  );
}
