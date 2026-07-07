"use client";

// Actual vs planned progress over time: each dated reading's real overall %
// against the time-based planned baseline for that date. Groupable by period.
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
  planned: number | null;
  breakdown: { total: number; completed: number; in_progress: number; not_started: number };
}

const PERIODS = [
  { value: "all", label: "All readings" },
  { value: "month", label: "By month" },
  { value: "quarter", label: "By quarter" },
  { value: "year", label: "By year" },
];

// Y axis in steps of 10 (100 at the top → 0 at the bottom).
const Y_TICKS = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0];

const monthYear = (iso: string) =>
  new Date(iso).toLocaleDateString("en", { month: "short", year: "2-digit" });

// Up to `max` evenly-spaced points, so the x-axis stays readable with many months.
function pickLabels<T>(points: T[], max = 8): T[] {
  if (points.length <= max) return points;
  const step = (points.length - 1) / (max - 1);
  return Array.from({ length: max }, (_, i) => points[Math.round(i * step)]);
}

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
          <h2 className={styles.title}>Progress over time</h2>
          <p className={styles.sub}>Actual progress vs the planned baseline.</p>
        </div>
        <Select className={styles.periodSelect} options={PERIODS} value={period}
          onChange={(e) => setPeriod(e.target.value)} aria-label="Group by period" />
      </header>

      <StateView
        loading={loading} error={error} isEmpty={points.length === 0}
        emptyTitle="No history yet"
        emptyText="Once progress is recorded on dated readings, actual-vs-planned shows here."
        onRetry={reload}
      >
        <div className={styles.legend}>
          <span className={styles.legendItem}><span className={`${styles.swatch} ${styles.swActual}`} />Actual</span>
          <span className={styles.legendItem}><span className={`${styles.swatch} ${styles.swPlanned}`} />Planned</span>
        </div>
        <div className={styles.chartCard}>
          <div className={styles.chartRow}>
            <div className={styles.yAxis}>
              {Y_TICKS.map((g) => <span key={g}>{g}</span>)}
            </div>
            <TrendChart points={points} />
          </div>
          {points.length > 0 && (
            <div className={styles.xAxis}>
              {pickLabels(points).map((s, i) => <span key={i}>{monthYear(s.date)}</span>)}
            </div>
          )}
        </div>
        <ul className={styles.list}>
          {[...points].reverse().map((s) => {
            const behind = s.planned != null && s.overall_progress < s.planned;
            return (
              <li key={s.date} className={styles.row}>
                <span className={styles.date}>{formatDate(s.date)}</span>
                <div className={styles.bar}>
                  <span className={styles.barFill} style={{ ["--pct" as string]: `${s.overall_progress}%` }} />
                  {s.planned != null && (
                    <span className={styles.plannedTick} style={{ ["--pct" as string]: `${s.planned}%` }}
                      title={`Planned ${s.planned}%`} />
                  )}
                </div>
                <span className={`${styles.pct} tnum ${behind ? styles.behind : ""}`}>
                  {s.overall_progress}%
                  {s.planned != null && <span className={styles.vsPlanned}> / {s.planned}%</span>}
                </span>
              </li>
            );
          })}
        </ul>
      </StateView>
    </section>
  );
}

// Actual (area + solid line) vs planned (dashed line). preserveAspectRatio="none"
// fills the width; lines and gridlines use non-scaling-stroke so they stay crisp.
// Axis labels are HTML, so they never distort.
function TrendChart({ points }: { points: Snapshot[] }) {
  const W = 800;
  const H = 220;
  const padY = 14;
  const xs = points.length;
  const x = (i: number) => (xs <= 1 ? W / 2 : (i * W) / (xs - 1));
  const y = (v: number) => H - padY - (v / 100) * (H - 2 * padY);

  const pathFor = (val: (s: Snapshot) => number) => {
    if (xs === 1) {
      const yy = y(val(points[0]));
      return `M 0 ${yy} L ${W} ${yy}`;
    }
    return points.map((s, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(val(s))}`).join(" ");
  };

  const actual = pathFor((s) => s.overall_progress);
  const hasPlanned = points.some((s) => s.planned != null);
  const planned = hasPlanned ? pathFor((s) => s.planned ?? 0) : "";
  const area = `${actual} L ${W} ${H} L 0 ${H} Z`;

  return (
    <div className={styles.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} preserveAspectRatio="none"
        role="img" aria-label="Actual vs planned progress over time">
        {Y_TICKS.map((g) => (
          <line key={g} x1={0} x2={W} y1={y(g)} y2={y(g)} className={styles.grid} vectorEffect="non-scaling-stroke" />
        ))}
        <path d={area} className={styles.area} />
        {planned && <path d={planned} className={styles.plannedLine} vectorEffect="non-scaling-stroke" />}
        <path d={actual} className={styles.trend} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
