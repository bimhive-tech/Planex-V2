"use client";

// Finances sub-tab: the P6 schedule's own cost/schedule-performance columns
// (Budgeted Total Cost, Earned Value Cost, Schedule Variance, durations,
// SPI) — imported onto every activity but otherwise unused anywhere else in
// the app. Read-only; there's nothing to edit here, it's a rollup of what
// the schedule import already brought in, plus the full per-activity detail.
import { StateView } from "@/components/ui/StateView";
import { api } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { ActivityScheduleTable } from "./ActivityScheduleTable";
import styles from "./finances.module.css";
import costStyles from "./projectCostPerformance.module.css";

interface CostPerformance {
  currency: string;
  budgeted_total_cost: string | null;
  earned_value_cost: string | null;
  schedule_variance: string | null;
}

function money(amount: string | null, currency: string): string {
  if (amount === null) return "—";
  const n = Number(amount);
  if (Number.isNaN(n)) return "—";
  const formatted = new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(Math.abs(n));
  return `${n < 0 ? "-" : ""}${currency ? `${currency} ` : ""}${formatted}`;
}

export function ProjectCostPerformance({ projectId }: { projectId: string }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<CostPerformance>(`/projects/${projectId}/cost-performance/`),
    [projectId],
  );

  const hasData = data && (data.budgeted_total_cost !== null || data.earned_value_cost !== null);

  return (
    <div className={styles.wrap}>
      <section className={styles.card}>
        <header className={styles.head}>
          <h2 className={styles.title}>
            Schedule Cost <span className={styles.muted}>(from the imported P6 schedule)</span>
          </h2>
        </header>

        <StateView
          loading={loading}
          error={error}
          isEmpty={!hasData}
          emptyTitle="No cost data imported"
          emptyText="Import a P6 schedule with Budgeted Total Cost / Earned Value Cost columns to see this."
          onRetry={reload}
        >
          {data && (
            <div className={costStyles.grid}>
              <div className={costStyles.stat}>
                <span className={costStyles.value}>{money(data.budgeted_total_cost, data.currency)}</span>
                <span className={costStyles.label}>Budgeted Total Cost</span>
              </div>
              <div className={costStyles.stat}>
                <span className={costStyles.value}>{money(data.earned_value_cost, data.currency)}</span>
                <span className={costStyles.label}>Earned Value Cost</span>
              </div>
              <div className={costStyles.stat}>
                <span className={`${costStyles.value} ${data.schedule_variance !== null && Number(data.schedule_variance) < 0 ? costStyles.negative : ""}`}>
                  {money(data.schedule_variance, data.currency)}
                </span>
                <span className={costStyles.label}>Schedule Variance</span>
              </div>
            </div>
          )}
        </StateView>
      </section>

      {hasData && <ActivityScheduleTable projectId={projectId} />}
    </div>
  );
}
