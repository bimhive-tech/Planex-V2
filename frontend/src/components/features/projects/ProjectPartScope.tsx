"use client";

// Part (Contracted Sub-Scope) tab — some contracts track a specific "Part" of
// the work (its own amount/baseline/forecast/delay) alongside the whole
// project. A log of entries, not a single snapshot: a project can have more
// than one over its life, so past ones stay visible as cards instead of
// being silently overwritten. Its own tab rather than buried in the
// edit-project drawer, since it's a distinct thing being tracked.
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import type { PartScope } from "@/types/project";
import { PartScopeModal } from "./PartScopeModal";
import styles from "./milestones.module.css";
import cardStyles from "./partScope.module.css";

function money(amount: string | null): string {
  if (amount === null) return "—";
  const n = Number(amount);
  return Number.isNaN(n) ? "—" : new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(n);
}

export function ProjectPartScope({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<PartScope[]>(`/projects/${projectId}/part-scopes/`),
    [projectId],
  );
  const [modal, setModal] = useState<{ entry: PartScope | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];

  async function remove(entry: PartScope, e: React.MouseEvent) {
    e.stopPropagation();
    if (!window.confirm(`Delete “${entry.title}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/part-scopes/${entry.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Part (Contracted Sub-Scope)</h2>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />}
            onClick={() => setModal({ entry: null })}>
            Add
          </Button>
        )}
      </header>
      <p className={cardStyles.hint}>
        Only add an entry if this contract tracks a specific &quot;Part&quot; of the work alongside the whole
        project — its own amount, baseline, forecast, and delay. A project can have more than one over time.
      </p>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={items.length === 0}
        emptyTitle="No Part Scope entries yet"
        emptyText={canManage ? "Add one if this contract tracks a specific Part alongside the whole project." : undefined}
        onRetry={reload}
      >
        <div className={cardStyles.grid}>
          {items.map((entry) => (
            <button key={entry.id} className={cardStyles.card} onClick={() => setModal({ entry })}>
              <div className={cardStyles.cardHead}>
                <span className={cardStyles.cardTitle}>{entry.title}</span>
                {canManage && (
                  <span className={cardStyles.delete} onClick={(e) => remove(entry, e)} role="button"
                    aria-label={`Delete ${entry.title}`}>
                    <Icon name="trash" size={14} />
                  </span>
                )}
              </div>
              <span className={cardStyles.amount}>{money(entry.amount)}</span>
              <div className={cardStyles.dates}>
                <span>Start: {entry.start_date ? formatDate(entry.start_date) : "—"}</span>
                <span>Baseline: {entry.completion_revised ? formatDate(entry.completion_revised) : "—"}</span>
                <span>Forecast: {entry.forecast_completion ? formatDate(entry.forecast_completion) : "—"}</span>
              </div>
              {entry.delay_days !== null && (
                <Badge tone={entry.delay_days > 0 ? "danger" : "success"}>
                  {entry.delay_days > 0 ? `${entry.delay_days} days late` : entry.delay_days < 0 ? `${-entry.delay_days} days ahead` : "On time"}
                </Badge>
              )}
            </button>
          ))}
        </div>
      </StateView>

      {modal && (
        <PartScopeModal projectId={projectId} entry={modal.entry}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}
