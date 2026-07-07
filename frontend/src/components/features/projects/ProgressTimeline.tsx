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
        <div className={styles.chartCard}>
          <div className={styles.chartRow}>
            <div className={styles.yAxis}><span>100</span><span>50</span><span>0</span></div>
            <TrendChart points={points} />
          </div>
          {points.length > 0 && (
            <div className={styles.xAxis}>
              <span>{formatDate(points[0].date)}</span>
              {points.length > 1 && <span>{formatDate(points[points.length - 1].date)}</span>}
            </div>
          )}
        </div>
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

// Area + line trend. preserveAspectRatio="none" fills the width; the line and
// gridlines use non-scaling-stroke so they stay crisp (no stretched, blobby
// dots — that's what made the old chart look bad). Axis labels are HTML, so
// they never distort.
function TrendChart({ points }: { points: Snapshot[] }) {
  const W = 800;
  const H = 220;
  const padY = 14;
  const xs = points.length;
  const x = (i: number) => (xs <= 1 ? W / 2 : (i * W) / (xs - 1));
  const y = (v: number) => H - padY - (v / 100) * (H - 2 * padY);

  let line: string;
  if (xs === 1) {
    const yy = y(points[0].overall_progress);
    line = `M 0 ${yy} L ${W} ${yy}`;
  } else {
    line = points.map((s, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(s.overall_progress)}`).join(" ");
  }
  const area = `${line} L ${W} ${H} L 0 ${H} Z`;

  return (
    <div className={styles.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} preserveAspectRatio="none"
        role="img" aria-label="Progress over time">
        {[0, 50, 100].map((g) => (
          <line key={g} x1={0} x2={W} y1={y(g)} y2={y(g)} className={styles.grid} vectorEffect="non-scaling-stroke" />
        ))}
        <path d={area} className={styles.area} />
        <path d={line} className={styles.trend} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
