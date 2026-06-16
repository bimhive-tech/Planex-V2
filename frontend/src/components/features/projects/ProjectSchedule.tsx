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
import { ScopeActivities } from "./ScopeActivities";
import { ZoneGridView } from "./ZoneGridView";
import styles from "./scheduleTree.module.css";

const NEXT_TYPE: Record<string, string> = { phase: "zone", zone: "building", building: "area", area: "area" };

interface Props {
  projectId: string;
  canManage: boolean;
  canSubmit: boolean;
  onStatsChange: (stats: { overall: number; breakdown: { total: number; completed: number; in_progress: number; not_started: number } }) => void;
}

export function ProjectSchedule({ projectId, canManage, canSubmit, onStatsChange }: Props) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectStructure>(`/projects/${projectId}/structure/`),
    [projectId],
  );

  // Bubble live stats (overall + status breakdown) up to the Overview tab.
  useEffect(() => {
    if (!data) return;
    onStatsChange({ overall: data.overall_progress, breakdown: data.progress_breakdown });
  }, [data, onStatsChange]);

  const [scopeModal, setScopeModal] = useState<{ parentId: string | null; scope: Scope | null; type: string } | null>(null);
  const [activityModal, setActivityModal] = useState<{ scopeId: string; activity: Activity | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [gridZone, setGridZone] = useState<{ id: string; name: string } | null>(null);
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
      const r = await api.upload<{ zones: number; subzones: number; activities: number; overall_progress: number; snapshot_date: string }>(
        `/upload/import/${projectId}`, file);
      setImportMsg(`Imported ${r.zones} zones, ${r.subzones} subzones, ${r.activities} task cells (${r.overall_progress}% overall) — snapshot dated ${r.snapshot_date}. Expand a subzone for its phases/tasks, or open the zone grid.`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  }

  const { childrenOf, progressOf, activityCountOf } = useMemo(() => buildTree(data), [data]);

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


  const roots = childrenOf.get(null) ?? [];

  if (gridZone) {
    return (
      <ZoneGridView
        projectId={projectId}
        zoneId={gridZone.id}
        zoneName={gridZone.name}
        canManage={canManage}
        onBack={() => setGridZone(null)}
        onChanged={reload}
      />
    );
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>
          {data ? `${data.scopes.length} scopes · ${data.activity_count} tasks · ${data.overall_progress}% overall` : "Structure"}
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
              projectId={projectId}
              childrenOf={childrenOf} progressOf={progressOf} activityCountOf={activityCountOf}
              canManage={canManage} canSubmit={canSubmit}
              onAddScope={(parentId, type) => setScopeModal({ parentId, scope: null, type })}
              onEditScope={(scope) => setScopeModal({ parentId: scope.parent, scope, type: scope.scope_type })}
              onDeleteScope={(scope) => del(`/projects/${projectId}/scopes/${scope.id}/`,
                `Delete “${scope.name}” and everything under it?`)}
              onAddActivity={(scopeId) => setActivityModal({ scopeId, activity: null })}
              onEditActivity={(activity) => setActivityModal({ scopeId: activity.scope, activity })}
              onChanged={reload}
              onOpenGrid={(id, name) => setGridZone({ id, name })}
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
  projectId: string;
  childrenOf: Map<string | null, Scope[]>;
  progressOf: (scopeId: string) => number;
  activityCountOf: Record<string, number>;
  canManage: boolean;
  canSubmit: boolean;
  onAddScope: (parentId: string, type: string) => void;
  onEditScope: (scope: Scope) => void;
  onDeleteScope: (scope: Scope) => void;
  onAddActivity: (scopeId: string) => void;
  onEditActivity: (activity: Activity) => void;
  onChanged: () => void;
  onOpenGrid: (id: string, name: string) => void;
}

function ScopeNode(props: NodeProps) {
  const { scope, depth, childrenOf, progressOf, activityCountOf, canManage } = props;
  const childScopes = childrenOf.get(scope.id) ?? [];
  const activityCount = activityCountOf[scope.id] ?? 0;
  // Collapse nodes with many children/tasks by default.
  const [open, setOpen] = useState(childScopes.length <= 25 && activityCount <= 25);
  const hasChildren = childScopes.length > 0 || activityCount > 0;
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
        {scope.scope_type === "zone" && childScopes.length > 0 && (
          <button className={styles.gridBtn} title="Open Excel grid" aria-label="Open Excel grid"
            onClick={() => props.onOpenGrid(scope.id, scope.name)}>
            <Icon name="dashboard" size={14} />
            <span>Grid</span>
          </button>
        )}
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
          {/* Leaf scope with tasks → lazy-load its activities. */}
          {childScopes.length === 0 && activityCount > 0 && (
            <ScopeActivities
              projectId={props.projectId} scopeId={scope.id} depth={depth + 1}
              canManage={canManage} canSubmit={props.canSubmit}
              onEdit={props.onEditActivity} onChanged={props.onChanged}
            />
          )}
        </>
      )}
    </div>
  );
}

// ── Tree helpers ────────────────────────────────────────────────────────────
function buildTree(data: ProjectStructure | null) {
  const childrenOf = new Map<string | null, Scope[]>();
  if (data) {
    for (const s of data.scopes) {
      const key = s.parent;
      if (!childrenOf.has(key)) childrenOf.set(key, []);
      childrenOf.get(key)!.push(s);
    }
  }
  const progress = data?.scope_progress ?? {};
  const progressOf = (scopeId: string): number => progress[scopeId] ?? 0;
  const activityCountOf = data?.scope_activity_counts ?? {};
  return { childrenOf, progressOf, activityCountOf };
}
