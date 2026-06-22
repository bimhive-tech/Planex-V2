"use client";

// "Tasks" filter for the Schedule tab: live search across the whole project's
// activities. Activities aren't preloaded with the structure — a zone tracker
// has tens of thousands of them — so this hits its own debounced, paginated
// backend search instead of filtering something already in memory.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { Activity, Scope } from "@/types/project";
import { SubmitProgressModal } from "./SubmitProgressModal";
import { UpdateProgressModal } from "./UpdateProgressModal";
import { scopePath } from "./scopeBreadcrumb";
import styles from "./scheduleTree.module.css";

interface Props {
  projectId: string;
  search: string;
  scopeById: Map<string, Scope>;
  canManage: boolean;
  canSubmit: boolean;
  onEdit: (activity: Activity) => void;
  onChanged: () => void; // refresh roll-ups (progress bars) upstream
}

export function ScheduleTaskSearch({ projectId, search, scopeById, canManage, canSubmit, onEdit, onChanged }: Props) {
  const [debounced, setDebounced] = useState(search);
  const [page, setPage] = useState(1);
  const [submitFor, setSubmitFor] = useState<Activity | null>(null);
  const [updateFor, setUpdateFor] = useState<Activity | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Debounce the search box (~300ms) so typing doesn't spam the API.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const trimmed = debounced.trim();
  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<Activity>>(
      `/projects/${projectId}/activities/search/?${new URLSearchParams({ q: trimmed, page: String(page) })}`,
    ),
    [projectId, trimmed, page],
  );
  const rows = data?.results ?? [];

  async function remove(a: Activity) {
    if (!window.confirm(`Delete task “${a.name}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/activities/${a.id}/`);
      reload();
      onChanged();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <>
      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={rows.length === 0}
        emptyTitle={trimmed.length < 2 ? "Keep typing…" : "No tasks found"}
        emptyText={trimmed.length < 2 ? "Type at least 2 characters to search tasks." : "Try a different search."}
      >
        {rows.map((a) => (
          <div key={a.id} className={styles.activityRow}>
            <div className={styles.flatNameBlock}>
              <span className={styles.breadcrumb}>{scopePath(a.scope, scopeById)}</span>
              <span className={styles.activityName}>
                {a.name}
                {a.code && <span className={styles.activityMeta}> · {a.code}</span>}
              </span>
            </div>
            <span className={`${styles.pct} tnum`}>{Math.round(Number(a.progress_percent))}%</span>
            {(canSubmit || canManage) && (
              <div className={styles.actions}>
                {canManage && (
                  <button className={styles.submitBtn} title="Record dated progress" onClick={() => setUpdateFor(a)}>
                    Update
                  </button>
                )}
                {canSubmit && (
                  <button className={styles.submitBtn} title="Submit progress for review" onClick={() => setSubmitFor(a)}>
                    Submit
                  </button>
                )}
                {canManage && (
                  <>
                    <button className={styles.actionBtn} aria-label="Edit task" onClick={() => onEdit(a)}>
                      <Icon name="edit" size={14} />
                    </button>
                    <button className={`${styles.actionBtn} ${styles.danger}`} aria-label="Delete task" onClick={() => remove(a)}>
                      <Icon name="trash" size={14} />
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </StateView>

      {data && (data.next || data.previous) && (
        <div className={styles.footer}>
          <span>{data.count} matching {data.count === 1 ? "task" : "tasks"} · page {page}</span>
          <div className={styles.pageBtns}>
            <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {submitFor && (
        <SubmitProgressModal projectId={projectId} activity={submitFor}
          onClose={() => setSubmitFor(null)} onSubmitted={onChanged} />
      )}
      {updateFor && (
        <UpdateProgressModal projectId={projectId} activity={updateFor}
          onClose={() => setUpdateFor(null)} onSaved={() => { reload(); onChanged(); }} />
      )}
    </>
  );
}
