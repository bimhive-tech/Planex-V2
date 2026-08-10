"use client";

// Key Milestones highlights (Overview): a short, curated slice of the
// project's milestones, plus add/edit/delete for managers. A P6 import can
// bring in hundreds of milestones (e.g. one per building handover) — this
// card stays short on purpose and points to the full Milestones tab instead
// of trying to render all of them here.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { MilestoneListItem } from "./MilestoneListItem";
import { MilestoneModal } from "./MilestoneModal";
import { milestoneCompletionPct, type Milestone } from "./milestoneShared";
import styles from "./milestones.module.css";

const OVERVIEW_CAP = 6;

export function MilestonesPanel({ projectId, canManage, onViewAll }: {
  projectId: string; canManage: boolean; onViewAll?: () => void;
}) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Milestone[]>(`/projects/${projectId}/milestones/`),
    [projectId],
  );
  const [modal, setModal] = useState<{ milestone: Milestone | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];
  const pct = milestoneCompletionPct(items);
  const shown = items.slice(0, OVERVIEW_CAP);
  const hasMore = items.length > OVERVIEW_CAP;

  async function remove(m: Milestone) {
    if (!window.confirm(`Delete milestone “${m.title}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/milestones/${m.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={`${styles.card}`}>
      <header className={styles.head}>
        <div className={styles.headTitleRow}>
          <h2 className={styles.title}>Key Milestones</h2>
          {pct !== null && <span className={styles.pctChip}>{pct}% complete</span>}
        </div>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />}
            onClick={() => setModal({ milestone: null })}>
            Add
          </Button>
        )}
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={items.length === 0}
        emptyTitle="No milestones yet"
        emptyText={canManage ? "Add key dates like kickoff, design approval, handover." : undefined}
        onRetry={reload}
      >
        <ul className={styles.list}>
          {shown.map((m) => (
            <MilestoneListItem key={m.id} milestone={m} canManage={canManage}
              onEdit={() => setModal({ milestone: m })} onDelete={() => remove(m)} />
          ))}
        </ul>
        {hasMore && onViewAll && (
          <button className={styles.viewAll} onClick={onViewAll}>
            View all {items.length} milestones →
          </button>
        )}
      </StateView>

      {modal && (
        <MilestoneModal projectId={projectId} milestone={modal.milestone}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}
