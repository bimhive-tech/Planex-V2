"use client";

// Lazily-loaded task rows under a leaf scope (e.g. a phase). Fetched on first
// expand — a zone tracker has tens of thousands of activities, so they never
// ship with the structure.
import { useEffect, useState, type CSSProperties } from "react";

import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import type { Activity } from "@/types/project";
import { SubmitProgressModal } from "./SubmitProgressModal";
import { UpdateProgressModal } from "./UpdateProgressModal";
import styles from "./scheduleTree.module.css";

interface Props {
  projectId: string;
  scopeId: string;
  depth: number;
  canManage: boolean;
  canSubmit: boolean;
  onEdit: (activity: Activity) => void;
  onChanged: () => void; // refresh roll-ups (progress bars) upstream
}

export function ScopeActivities({ projectId, scopeId, depth, canManage, canSubmit, onEdit, onChanged }: Props) {
  const [acts, setActs] = useState<Activity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitFor, setSubmitFor] = useState<Activity | null>(null);
  const [updateFor, setUpdateFor] = useState<Activity | null>(null);

  async function load() {
    try {
      setActs(await api.get<Activity[]>(`/projects/${projectId}/scopes/${scopeId}/activities/`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load tasks.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, scopeId]);

  async function remove(a: Activity) {
    if (!window.confirm(`Delete task “${a.name}”?`)) return;
    try {
      await api.del(`/projects/${projectId}/activities/${a.id}/`);
      load();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  if (error) return <div className={styles.activityRow} style={indent(depth)}><span className="formError">{error}</span></div>;
  if (acts === null) return <div className={styles.activityRow} style={indent(depth)}><span className={styles.activityMeta}>Loading tasks…</span></div>;

  return (
    <>
      {acts.map((a) => (
        <div key={a.id} className={styles.activityRow} style={indent(depth)}>
          <span className={styles.activityName}>
            {a.name}
            {a.code && <span className={styles.activityMeta}> · {a.code}</span>}
            <span className={styles.activityMeta}> · w{a.weight}</span>
          </span>
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
      {submitFor && (
        <SubmitProgressModal
          projectId={projectId} activity={submitFor}
          onClose={() => setSubmitFor(null)} onSubmitted={onChanged}
        />
      )}
      {updateFor && (
        <UpdateProgressModal
          projectId={projectId} activity={updateFor}
          onClose={() => setUpdateFor(null)}
          onSaved={() => { load(); onChanged(); }}
        />
      )}
    </>
  );
}

const indent = (depth: number) => ({ "--depth": String(depth) } as CSSProperties);
