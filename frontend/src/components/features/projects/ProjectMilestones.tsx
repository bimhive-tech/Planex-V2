"use client";

// Full Milestones tab: every milestone on the project, searchable and
// grouped by the zone/building a P6 import tied it to (when it has one) —
// the Overview card only ever shows a short curated slice of this list.
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { MilestoneListItem } from "./MilestoneListItem";
import { MilestoneModal } from "./MilestoneModal";
import { MILESTONE_STATUSES, milestoneCompletionPct, type Milestone } from "./milestoneShared";
import panelStyles from "./milestones.module.css";
import styles from "./projectMilestones.module.css";

const GENERAL_GROUP = "Project-wide";
const STATUS_FILTER_OPTIONS = [{ value: "", label: "All statuses" }, ...MILESTONE_STATUSES];

function groupLabel(m: Milestone): string {
  return m.scope_path && m.scope_path.length > 0 ? m.scope_path.join(" / ") : GENERAL_GROUP;
}

export function ProjectMilestones({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Milestone[]>(`/projects/${projectId}/milestones/`),
    [projectId],
  );
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [modal, setModal] = useState<{ milestone: Milestone | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const filtered = useMemo(() => {
    const q = debounced.trim().toLowerCase();
    return items.filter((m) => {
      if (statusFilter && m.status !== statusFilter) return false;
      if (!q) return true;
      return m.title.toLowerCase().includes(q) || groupLabel(m).toLowerCase().includes(q);
    });
  }, [items, debounced, statusFilter]);

  const groups = useMemo(() => {
    const map = new Map<string, Milestone[]>();
    for (const m of filtered) {
      const key = groupLabel(m);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(m);
    }
    const entries = [...map.entries()];
    // General (project-wide) milestones first, then groups alphabetically.
    entries.sort(([a], [b]) => (a === GENERAL_GROUP ? -1 : b === GENERAL_GROUP ? 1 : a.localeCompare(b)));
    return entries;
  }, [filtered]);

  const pct = milestoneCompletionPct(items);

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
    <section className={panelStyles.card}>
      <header className={panelStyles.head}>
        <div className={panelStyles.headTitleRow}>
          <h2 className={panelStyles.title}>Milestones</h2>
          <span className={styles.count}>
            {items.length} total{pct !== null ? ` · ${pct}% complete` : ""}
          </span>
        </div>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />}
            onClick={() => setModal({ milestone: null })}>
            Add
          </Button>
        )}
      </header>

      <div className={styles.filterRow}>
        <input
          className={styles.search}
          type="search"
          placeholder="Search milestones…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search milestones"
        />
        <Select options={STATUS_FILTER_OPTIONS} value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status" />
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={items.length === 0}
        emptyTitle="No milestones yet"
        emptyText={canManage ? "Add key dates like kickoff, design approval, handover — or import a P6 schedule." : undefined}
        onRetry={reload}
      >
        {groups.length === 0 ? (
          <p className={styles.noMatches}>No milestones match the current filter.</p>
        ) : (
          <div className={styles.groups}>
            {groups.map(([label, ms]) => (
              <section key={label} className={styles.group}>
                <h3 className={styles.groupTitle}>
                  {label} <span className={styles.groupCount}>{ms.length}</span>
                </h3>
                <ul className={panelStyles.list}>
                  {ms.map((m) => (
                    <MilestoneListItem key={m.id} milestone={m} canManage={canManage}
                      onEdit={() => setModal({ milestone: m })} onDelete={() => remove(m)} />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </StateView>

      {modal && (
        <MilestoneModal projectId={projectId} milestone={modal.milestone}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}
