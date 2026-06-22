"use client";

// Schedule tab: the project's work hierarchy (Phase -> Zone -> Building -> Area ->
// Activity). Build the tree, set per-activity progress; everything rolls up.
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { Activity, ProjectStructure, Scope } from "@/types/project";
import { ScopeFormModal } from "./ScopeFormModal";
import { ActivityFormModal } from "./ActivityFormModal";
import { ZoneGridView } from "./ZoneGridView";
import { ProgressGalleryModal } from "./ProgressGalleryModal";
import { ScheduleFilterBar, type ScheduleFilterType } from "./ScheduleFilterBar";
import { ScheduleFlatList } from "./ScheduleFlatList";
import { ScheduleTaskSearch } from "./ScheduleTaskSearch";
import { ScopeNode } from "./ScopeTreeNode";
import { scopeById as buildScopeById } from "./scopeBreadcrumb";
import { buildTree } from "./scheduleTreeUtils";
import styles from "./scheduleTree.module.css";

interface Props {
  projectId: string;
  canManage: boolean;
  canSubmit: boolean;
  canDeletePhotos: boolean;
  onStatsChange: (stats: { overall: number; breakdown: { total: number; completed: number; in_progress: number; not_started: number } }) => void;
}

export function ProjectSchedule({ projectId, canManage, canSubmit, canDeletePhotos, onStatsChange }: Props) {
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
  const [filterType, setFilterType] = useState<ScheduleFilterType>("all");
  const [filterSearch, setFilterSearch] = useState("");
  const [photosScope, setPhotosScope] = useState<{ id: string; name: string } | null>(null);
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
  const scopeByIdMap = useMemo(() => buildScopeById(data?.scopes ?? []), [data]);
  const scopeIdsWithChildren = useMemo(
    () => new Set([...childrenOf.keys()].filter((k): k is string => k !== null)),
    [childrenOf],
  );
  const flatScopes = useMemo(() => {
    if (filterType === "all" || filterType === "task" || !data) return [];
    const q = filterSearch.trim().toLowerCase();
    return data.scopes
      .filter((s) => s.scope_type === filterType && (!q || s.name.toLowerCase().includes(q)))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [data, filterType, filterSearch]);

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

      <ScheduleFilterBar
        type={filterType}
        onTypeChange={(t) => { setFilterType(t); setFilterSearch(""); }}
        search={filterSearch}
        onSearchChange={setFilterSearch}
      />

      <div className={styles.surface}>
        <StateView
          loading={loading}
          error={error}
          isEmpty={filterType === "all" ? roots.length === 0 : filterType !== "task" && flatScopes.length === 0}
          emptyTitle={filterType === "all" ? "No structure yet" : "No matches"}
          emptyText={
            filterType === "all"
              ? (canManage ? "Add a phase, then zones and activities under it." : "Nothing has been set up yet.")
              : (filterSearch.trim() ? "Try a different search." : "Nothing of this type in the project yet.")
          }
          onRetry={reload}
        >
          {filterType === "all" && roots.map((s) => (
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
              onOpenPhotos={(id, name) => setPhotosScope({ id, name })}
            />
          ))}

          {filterType !== "all" && filterType !== "task" && (
            <ScheduleFlatList
              scopes={flatScopes}
              scopeIdsWithChildren={scopeIdsWithChildren}
              scopeById={scopeByIdMap}
              progressOf={progressOf}
              canManage={canManage}
              onEditScope={(scope) => setScopeModal({ parentId: scope.parent, scope, type: scope.scope_type })}
              onDeleteScope={(scope) => del(`/projects/${projectId}/scopes/${scope.id}/`,
                `Delete “${scope.name}” and everything under it?`)}
              onOpenGrid={(id, name) => setGridZone({ id, name })}
              onOpenPhotos={(id, name) => setPhotosScope({ id, name })}
            />
          )}

          {filterType === "task" && (
            <ScheduleTaskSearch
              projectId={projectId}
              search={filterSearch}
              scopeById={scopeByIdMap}
              canManage={canManage}
              canSubmit={canSubmit}
              onEdit={(activity) => setActivityModal({ scopeId: activity.scope, activity })}
              onChanged={reload}
            />
          )}
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
      {photosScope && (
        <ProgressGalleryModal
          projectId={projectId} scope={photosScope} canDelete={canDeletePhotos}
          onClose={() => setPhotosScope(null)}
        />
      )}
    </div>
  );
}
