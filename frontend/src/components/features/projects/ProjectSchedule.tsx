"use client";

// Schedule tab: the project's work hierarchy (Phase -> Zone -> Building -> Area ->
// Activity). Build the tree, set per-activity progress; everything rolls up.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { Activity, ProjectStructure, Scope } from "@/types/project";
import { ScopeFormModal } from "./ScopeFormModal";
import { ActivityFormModal } from "./ActivityFormModal";
import styles from "./scheduleTree.module.css";

const NEXT_TYPE: Record<string, string> = { phase: "zone", zone: "building", building: "area", area: "area" };

interface Props {
  projectId: string;
  canManage: boolean;
  onOverallChange: (value: number) => void;
}

export function ProjectSchedule({ projectId, canManage, onOverallChange }: Props) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectStructure>(`/projects/${projectId}/structure/`),
    [projectId],
  );

  // Bubble the live overall up to the donut on the Overview tab.
  useEffect(() => {
    if (data) onOverallChange(data.overall_progress);
  }, [data, onOverallChange]);

  const [scopeModal, setScopeModal] = useState<{ parentId: string | null; scope: Scope | null; type: string } | null>(null);
  const [activityModal, setActivityModal] = useState<{ scopeId: string; activity: Activity | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    if (data && data.scopes.length > 0 &&
        !window.confirm("Importing replaces the current structure. Continue?")) return;
    setImporting(true);
    setActionError(null);
    setImportMsg(null);
    try {
      const r = await api.upload<{ zones: number; activities: number; overall_progress: number }>(
        `/upload/import/${projectId}`, file);
      setImportMsg(`Imported ${r.zones} zones and ${r.activities} activities (${r.overall_progress}% overall).`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  }

  const { childrenOf, activitiesOf, progressOf } = useMemo(() => buildTree(data), [data]);

  async function del(url: string, confirmText: string) {
    if (!window.confirm(confirmText)) return;
    setActionError(null);
    try {
      await api.del(url);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  async function setProgress(activity: Activity, value: string) {
    const v = Math.max(0, Math.min(100, Number(value)));
    if (Number.isNaN(v) || String(v) === activity.progress_percent) return;
    setActionError(null);
    try {
      await api.patch(`/projects/${projectId}/activities/${activity.id}/`, { progress_percent: v });
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't save progress.");
    }
  }

  const roots = childrenOf.get(null) ?? [];

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>
          {data ? `${data.scopes.length} scopes · ${data.activities.length} activities · ${data.overall_progress}% overall` : "Structure"}
        </span>
        {canManage && (
          <div className={styles.toolbarActions}>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm" hidden onChange={handleImport} />
            <Button size="sm" variant="secondary" disabled={importing}
              onClick={() => fileRef.current?.click()}>
              {importing ? "Importing…" : "Import Excel"}
            </Button>
            <Button size="sm" leadingIcon={<Icon name="plus" size={16} />}
              onClick={() => setScopeModal({ parentId: null, scope: null, type: "phase" })}>
              Add phase
            </Button>
          </div>
        )}
      </div>

      {importMsg && <p className={styles.importMsg}>{importMsg}</p>}
      {actionError && <p className="formError">{actionError}</p>}

      <div className={styles.surface}>
        <StateView
          loading={loading}
          error={error}
          isEmpty={roots.length === 0}
          emptyTitle="No structure yet"
          emptyText={canManage ? "Add a phase, then zones and activities under it." : "Nothing has been set up yet."}
          onRetry={reload}
        >
          {roots.map((s) => (
            <ScopeNode
              key={s.id} scope={s} depth={0}
              childrenOf={childrenOf} activitiesOf={activitiesOf} progressOf={progressOf}
              canManage={canManage}
              onAddScope={(parentId, type) => setScopeModal({ parentId, scope: null, type })}
              onEditScope={(scope) => setScopeModal({ parentId: scope.parent, scope, type: scope.scope_type })}
              onDeleteScope={(scope) => del(`/projects/${projectId}/scopes/${scope.id}/`,
                `Delete “${scope.name}” and everything under it?`)}
              onAddActivity={(scopeId) => setActivityModal({ scopeId, activity: null })}
              onEditActivity={(activity) => setActivityModal({ scopeId: activity.scope, activity })}
              onDeleteActivity={(activity) => del(`/projects/${projectId}/activities/${activity.id}/`,
                `Delete activity “${activity.name}”?`)}
              onSetProgress={setProgress}
            />
          ))}
        </StateView>
      </div>

      {scopeModal && (
        <ScopeFormModal
          open onClose={() => setScopeModal(null)} onSaved={reload}
          projectId={projectId} parentId={scopeModal.parentId} scope={scopeModal.scope}
          defaultType={scopeModal.type}
        />
      )}
      {activityModal && (
        <ActivityFormModal
          open onClose={() => setActivityModal(null)} onSaved={reload}
          projectId={projectId} scopeId={activityModal.scopeId} activity={activityModal.activity}
        />
      )}
    </div>
  );
}

// ── Tree node ───────────────────────────────────────────────────────────────
interface NodeProps {
  scope: Scope;
  depth: number;
  childrenOf: Map<string | null, Scope[]>;
  activitiesOf: Map<string, Activity[]>;
  progressOf: (scopeId: string) => number;
  canManage: boolean;
  onAddScope: (parentId: string, type: string) => void;
  onEditScope: (scope: Scope) => void;
  onDeleteScope: (scope: Scope) => void;
  onAddActivity: (scopeId: string) => void;
  onEditActivity: (activity: Activity) => void;
  onDeleteActivity: (activity: Activity) => void;
  onSetProgress: (activity: Activity, value: string) => void;
}

function ScopeNode(props: NodeProps) {
  const { scope, depth, childrenOf, activitiesOf, progressOf, canManage } = props;
  const [open, setOpen] = useState(true);
  const childScopes = childrenOf.get(scope.id) ?? [];
  const activities = activitiesOf.get(scope.id) ?? [];
  const hasChildren = childScopes.length > 0 || activities.length > 0;
  const pct = progressOf(scope.id);
  const indent = { "--depth": String(depth) } as CSSProperties;

  return (
    <div>
      <div className={styles.scopeRow} style={indent}>
        <button className={styles.caret} onClick={() => setOpen((o) => !o)} aria-label={open ? "Collapse" : "Expand"}>
          {hasChildren ? <Icon name="chevronDown" size={14} className={open ? "" : styles.caretClosed} /> : <span className={styles.dot} />}
        </button>
        <Badge tone="info">{scope.scope_type_display}</Badge>
        <span className={styles.scopeName}>{scope.name}</span>
        <div className={styles.bar}><span className={styles.barFill} style={{ ["--pct" as string]: `${pct}%` }} /></div>
        <span className={`${styles.pct} tnum`}>{pct}%</span>
        {canManage && (
          <div className={styles.actions}>
            <button className={styles.actionBtn} title="Add sub-level" aria-label="Add sub-level"
              onClick={() => props.onAddScope(scope.id, NEXT_TYPE[scope.scope_type])}>
              <Icon name="plus" size={14} />
            </button>
            <button className={styles.actionBtn} title="Add activity" aria-label="Add activity"
              onClick={() => props.onAddActivity(scope.id)}>
              <Icon name="projects" size={14} />
            </button>
            <button className={styles.actionBtn} title="Rename" aria-label="Rename"
              onClick={() => props.onEditScope(scope)}>
              <Icon name="edit" size={14} />
            </button>
            <button className={`${styles.actionBtn} ${styles.danger}`} title="Delete" aria-label="Delete"
              onClick={() => props.onDeleteScope(scope)}>
              <Icon name="trash" size={14} />
            </button>
          </div>
        )}
      </div>

      {open && (
        <>
          {childScopes.map((c) => <ScopeNode key={c.id} {...props} scope={c} depth={depth + 1} />)}
          {activities.map((a) => (
            <div key={a.id} className={styles.activityRow} style={{ "--depth": String(depth + 1) } as CSSProperties}>
              <span className={styles.activityName}>
                {a.name}
                {a.code && <span className={styles.activityMeta}> · {a.code}</span>}
                {a.unit && <span className={styles.activityMeta}> · {a.unit}</span>}
                <span className={styles.activityMeta}> · w{a.weight}</span>
              </span>
              {canManage ? (
                <input
                  key={a.progress_percent}
                  className={styles.progressInput}
                  type="number" min="0" max="100" step="1"
                  defaultValue={a.progress_percent}
                  onBlur={(e) => props.onSetProgress(a, e.target.value)}
                  aria-label={`Progress for ${a.name}`}
                />
              ) : (
                <span className={`${styles.pct} tnum`}>{a.progress_percent}%</span>
              )}
              {canManage && (
                <div className={styles.actions}>
                  <button className={styles.actionBtn} title="Edit" aria-label="Edit activity"
                    onClick={() => props.onEditActivity(a)}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button className={`${styles.actionBtn} ${styles.danger}`} title="Delete" aria-label="Delete activity"
                    onClick={() => props.onDeleteActivity(a)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── Tree helpers ────────────────────────────────────────────────────────────
function buildTree(data: ProjectStructure | null) {
  const childrenOf = new Map<string | null, Scope[]>();
  const activitiesOf = new Map<string, Activity[]>();
  if (data) {
    for (const s of data.scopes) {
      const key = s.parent;
      if (!childrenOf.has(key)) childrenOf.set(key, []);
      childrenOf.get(key)!.push(s);
    }
    for (const a of data.activities) {
      if (!activitiesOf.has(a.scope)) activitiesOf.set(a.scope, []);
      activitiesOf.get(a.scope)!.push(a);
    }
  }

  // Weighted progress over a scope's whole subtree.
  const progressOf = (scopeId: string): number => {
    let wsum = 0;
    let psum = 0;
    const walk = (id: string) => {
      for (const a of activitiesOf.get(id) ?? []) {
        const w = Number(a.weight) || 0;
        wsum += w;
        psum += w * (Number(a.progress_percent) || 0);
      }
      for (const c of childrenOf.get(id) ?? []) walk(c.id);
    };
    walk(scopeId);
    return wsum ? Math.round((psum / wsum) * 10) / 10 : 0;
  };

  return { childrenOf, activitiesOf, progressOf };
}
