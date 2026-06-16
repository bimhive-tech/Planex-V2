"use client";

// Progress over time: dated snapshots (one per import) plotted as a trend, with a
// month/quarter/year grouping. Lets you see progress as of any captured date.
import { useMemo, useState } from "react";

import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import styles from "./progressTimeline.module.css";

interface Snapshot {
  date: string;
  overall_progress: number;
  breakdown: { total: number; completed: number; in_progress: number; not_started: number };
}

const PERIODS = [
  { value: "all", label: "All snapshots" },
  { value: "month", label: "By month" },
  { value: "quarter", label: "By quarter" },
  { value: "year", label: "By year" },
];

function periodKey(iso: string, period: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  if (period === "year") return `${y}`;
  if (period === "quarter") return `${y}-Q${Math.floor(d.getMonth() / 3) + 1}`;
  return `${y}-${String(d.getMonth() + 1).padStart(2, "0")}`; // month
}

export function ProgressTimeline({ projectId }: { projectId: string }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Snapshot[]>(`/projects/${projectId}/snapshots/`),
    [projectId],
  );
  const [period, setPeriod] = useState("all");

  const points = useMemo(() => {
    const snaps = data ?? [];
    if (period === "all") return snaps;
    // Keep the last snapshot in each period.
    const byKey = new Map<string, Snapshot>();
    for (const s of snaps) byKey.set(periodKey(s.date, period), s);
    return [...byKey.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [data, period]);

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <div>
          <h2 className={styles.title}>Progress Timeline</h2>
          <p className={styles.sub}>Captured on each Excel import.</p>
        </div>
        <Select className={styles.periodSelect} options={PERIODS} value={period}
          onChange={(e) => setPeriod(e.target.value)} aria-label="Group by period" />
      </header>

      <StateView
        loading={loading} error={error} isEmpty={points.length === 0}
        emptyTitle="No history yet"
        emptyText="Import a dated tracker (the date is read from the file name) to start the timeline."
        onRetry={reload}
      >
        <TrendChart points={points} />
        <ul className={styles.list}>
          {[...points].reverse().map((s) => (
            <li key={s.date} className={styles.row}>
              <span className={styles.date}>{formatDate(s.date)}</span>
              <div className={styles.bar}>
                <span className={styles.barFill} style={{ ["--pct" as string]: `${s.overall_progress}%` }} />
              </div>
              <span className={`${styles.pct} tnum`}>{s.overall_progress}%</span>
            </li>
          ))}
        </ul>
      </StateView>
    </section>
  );
}

function TrendChart({ points }: { points: Snapshot[] }) {
  const W = 640;
  const H = 160;
  const pad = 28;
  const xs = points.length;
  const x = (i: number) => (xs <= 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (xs - 1));
  const y = (v: number) => H - pad - (v / 100) * (H - 2 * pad);
  const line = points.map((s, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(s.overall_progress)}`).join(" ");

  return (
    <div className={styles.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} preserveAspectRatio="none">
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <line x1={pad} x2={W - pad} y1={y(g)} y2={y(g)} className={styles.grid} />
            <text x={2} y={y(g) + 3} className={styles.axis}>{g}</text>
          </g>
        ))}
        {points.length > 1 && <path d={line} className={styles.trend} />}
        {points.map((s, i) => (
          <circle key={s.date} cx={x(i)} cy={y(s.overall_progress)} r={4} className={styles.point} />
        ))}
      </svg>
    </div>
  );
}
