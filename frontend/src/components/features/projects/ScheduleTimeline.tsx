"use client";

// Visual schedule health: compares time elapsed vs work done, and plots start,
// planned finish, revised finish and "today" on one track — the at-a-glance
// picture a PM actually wants from the overview.
import { formatDate } from "@/lib/format";
import styles from "./scheduleTimeline.module.css";

const DAY = 1000 * 60 * 60 * 24;

export function ScheduleTimeline({ start, finish, revised, progress }: {
  start: string | null; finish: string | null; revised: string | null; progress: number;
}) {
  if (!start || !finish) {
    return <p className={styles.empty}>Add a planned start and finish to see the schedule.</p>;
  }
  const s = new Date(start).getTime();
  const f = new Date(finish).getTime();
  const r = revised ? new Date(revised).getTime() : null;
  const now = Date.now();
  const spanEnd = Math.max(f, r ?? f, now);
  const span = Math.max(1, spanEnd - s);
  const at = (t: number) => Math.max(0, Math.min(100, ((t - s) / span) * 100));

  const totalDays = Math.max(1, Math.round((f - s) / DAY));
  const elapsedDays = Math.max(0, Math.round((Math.min(now, f) - s) / DAY));
  const remaining = Math.round((f - now) / DAY);
  const timePct = Math.min(100, Math.round((elapsedDays / totalDays) * 100));
  const workPct = Math.round(progress);
  const overdue = now > f;
  const delta = workPct - timePct; // + ahead of plan, − behind
  const verdict =
    delta >= 5 ? { tone: "ahead", text: `Ahead of schedule by ${delta}%` }
    : delta <= -5 ? { tone: "behind", text: `Behind schedule by ${-delta}%` }
    : { tone: "ontrack", text: "On track with the plan" };

  return (
    <div className={styles.wrap}>
      <span className={`${styles.verdict} ${styles[verdict.tone]}`}>{verdict.text}</span>

      <div className={styles.compare}>
        <Bar label="Time elapsed" pct={timePct} tone="time" />
        <Bar label="Work done" pct={workPct} tone="work" />
      </div>

      <div className={styles.track}>
        <span className={styles.elapsed} style={{ ["--x" as string]: `${at(now)}%` }} />
        <Marker x={at(f)} tone="planned" title={`Planned finish · ${formatDate(finish)}`} />
        {r && revised && r !== f && (
          <Marker x={at(r)} tone="revised" title={`Revised finish · ${formatDate(revised)}`} />
        )}
        <span className={styles.today} style={{ ["--x" as string]: `${at(now)}%` }} title="Today" />
      </div>

      <div className={styles.legend}>
        <Leg tone="start" label="Start" value={formatDate(start)} />
        <Leg tone="planned" label="Planned finish" value={formatDate(finish)} />
        {revised && <Leg tone="revised" label="Revised finish" value={formatDate(revised)} />}
        <Leg tone={overdue ? "behind" : "ontrack"}
          label={overdue ? "Overdue by" : "Days remaining"}
          value={`${Math.abs(remaining).toLocaleString()} days`} />
      </div>
    </div>
  );
}

function Bar({ label, pct, tone }: { label: string; pct: number; tone: string }) {
  return (
    <div className={styles.barRow}>
      <span className={styles.barLabel}>{label}</span>
      <div className={styles.bar}>
        <span className={`${styles.barFill} ${styles[`fill_${tone}`]}`} style={{ ["--pct" as string]: `${pct}%` }} />
      </div>
      <span className={`${styles.barPct} tnum`}>{pct}%</span>
    </div>
  );
}

function Marker({ x, tone, title }: { x: number; tone: string; title: string }) {
  return <span className={`${styles.marker} ${styles[`mk_${tone}`]}`} style={{ ["--x" as string]: `${x}%` }} title={title} />;
}

function Leg({ tone, label, value }: { tone: string; label: string; value: string }) {
  return (
    <div className={styles.legItem}>
      <span className={`${styles.dot} ${styles[`dot_${tone}`]}`} aria-hidden="true" />
      <span className={styles.legLabel}>{label}</span>
      <span className={styles.legValue}>{value}</span>
    </div>
  );
}
