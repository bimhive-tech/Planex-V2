"use client";

// Schedule tab: the project's work hierarchy (Phase -> Zone -> Building -> Area ->
// Activity). Build the tree, set per-activity progress; everything rolls up. A
// Zone/Subzone/Phase/Task filter bar prunes both the tree and the Excel grid
// down to one branch.
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
import { ScheduleFilterBar } from "./ScheduleFilterBar";
import { ScopeNode } from "./ScopeTreeNode";
import { buildTree, resolveScheduleFilter } from "./scheduleTreeUtils";
import styles from "./scheduleTree.module.css";

interface Props {
  projectId: string;
  canManage: boolean;
  canSubmit: boolean;
  canDeletePhotos: boolean;
  onStatsChange: (stats: { overall: number; breakdown: { total: number; completed: number; in_progress: number; not_started: number } }) => void;
}

export function ProjectSchedule({ projectId, canManage, canSubmit, canDeletePhotos, onStatsChange }: Props) {
  // As-of / month view mode. "current" = live; "asof" = cumulative up to the end
  // of a month; "month" = only the progress that moved during that month.
  const [viewMode, setViewMode] = useState<"current" | "asof" | "month">("current");
  const [viewMonth, setViewMonth] = useState(""); // "YYYY-MM"
  const viewQuery = useMemo(() => {
    if (viewMode === "current" || !viewMonth) return "";
    const [y, m] = viewMonth.split("-").map(Number);
    if (viewMode === "asof") {
      const end = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10); // last day of the month
      return `?mode=asof&as_of=${end}`;
    }
    return `?mode=month&as_of=${viewMonth}-01`;
  }, [viewMode, viewMonth]);

  function pickMode(mode: "current" | "asof" | "month") {
    setViewMode(mode);
    if (mode !== "current" && !viewMonth) setViewMonth(new Date().toISOString().slice(0, 7));
  }

  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectStructure>(`/projects/${projectId}/structure/${viewQuery}`),
    [projectId, viewQuery],
  );

  // Bubble live stats up to the Overview — only in the current view; the as-of /
  // month views are historical and shouldn't change the Overview's headline.
  useEffect(() => {
    if (!data || viewMode !== "current") return;
    onStatsChange({ overall: data.overall_progress, breakdown: data.progress_breakdown });
  }, [data, viewMode, onStatsChange]);

  const [scopeModal, setScopeModal] = useState<{ parentId: string | null; scope: Scope | null; type: string } | null>(null);
  const [activityModal, setActivityModal] = useState<{ scopeId: string; activity: Activity | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [gridZone, setGridZone] = useState<{ id: string; name: string } | null>(null);
  const [photosScope, setPhotosScope] = useState<{ id: string; name: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [scheduleImporting, setScheduleImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const scheduleFileRef = useRef<HTMLInputElement>(null);

  const [zoneFilter, setZoneFilter] = useState("");
  const [subzoneFilter, setSubzoneFilter] = useState("");
  const [phaseFilter, setPhaseFilter] = useState("");
  const [taskFilter, setTaskFilter] = useState("");

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

  async function handleScheduleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setScheduleImporting(true);
    setActionError(null);
    setImportMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.uploadApi<{ matched: number; unmatched: number; total_rows: number }>(
        `/projects/${projectId}/schedule-import/`, form);
      setImportMsg(`Matched ${r.matched} of ${r.total_rows} schedule rows to existing zones/phases (${r.unmatched} unmatched). Dates are now set on the matching scopes.`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Schedule import failed.");
    } finally {
      setScheduleImporting(false);
    }
  }

  const { childrenOf, progressOf, activityCountOf } = useMemo(() => buildTree(data), [data]);
  const roots = childrenOf.get(null) ?? [];

  const zoneOptions = useMemo(() => roots.filter((s) => s.scope_type === "zone"), [roots]);
  const { visibleIds, subzoneScope, phaseScope } = useMemo(
    () => resolveScheduleFilter(childrenOf, zoneFilter, subzoneFilter, phaseFilter),
    [childrenOf, zoneFilter, subzoneFilter, phaseFilter],
  );
  const subzoneOptions = useMemo(
    () => (zoneFilter ? (childrenOf.get(zoneFilter) ?? []).filter((s) => s.scope_type === "building" || s.scope_type === "area") : []),
    [childrenOf, zoneFilter],
  );
  const phaseOptions = useMemo(
    () => (subzoneScope ? (childrenOf.get(subzoneScope.id) ?? []).filter((s) => s.scope_type === "phase") : []),
    [childrenOf, subzoneScope],
  );
  // Reuses the existing lazy per-scope activities endpoint — no global fetch needed.
  const { data: taskOptions } = useFetch(
    () => (phaseScope ? api.get<Activity[]>(`/projects/${projectId}/scopes/${phaseScope.id}/activities/`) : Promise.resolve([] as Activity[])),
    [projectId, phaseScope?.id],
  );

  function handleZoneFilter(value: string) {
    setZoneFilter(value);
    setSubzoneFilter("");
    setPhaseFilter("");
    setTaskFilter("");
    if (gridZone) {
      const z = zoneOptions.find((s) => s.id === value);
      setGridZone(z ? { id: z.id, name: z.name } : null);
    }
  }
  function handleSubzoneFilter(value: string) {
    setSubzoneFilter(value);
    setPhaseFilter("");
    setTaskFilter("");
  }
  function handlePhaseFilter(value: string) {
    setPhaseFilter(value);
    setTaskFilter("");
  }

  function openGrid(id: string, name: string) {
    setGridZone({ id, name });
    if (zoneFilter !== id) {
      setZoneFilter(id);
      setSubzoneFilter("");
      setPhaseFilter("");
      setTaskFilter("");
    }
  }

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

  const visibleRoots = roots.filter((s) => !visibleIds || visibleIds.has(s.id));

  const filterBar = (
    <ScheduleFilterBar
      zoneOptions={zoneOptions}
      subzoneOptions={subzoneOptions}
      phaseOptions={phaseOptions}
      taskOptions={taskOptions ?? []}
      zone={zoneFilter} subzone={subzoneFilter} phase={phaseFilter} task={taskFilter}
      onZoneChange={handleZoneFilter}
      onSubzoneChange={handleSubzoneFilter}
      onPhaseChange={handlePhaseFilter}
      onTaskChange={setTaskFilter}
    />
  );

  const thisMonth = new Date().toISOString().slice(0, 7);
  const viewControls = (
    <div className={styles.viewBar}>
      <div className={styles.segmented}>
        <button type="button" className={`${styles.seg} ${viewMode === "current" ? styles.segOn : ""}`}
          onClick={() => pickMode("current")}>Current</button>
        <button type="button" className={`${styles.seg} ${viewMode === "asof" ? styles.segOn : ""}`}
          onClick={() => pickMode("asof")}>Up to month</button>
        <button type="button" className={`${styles.seg} ${viewMode === "month" ? styles.segOn : ""}`}
          onClick={() => pickMode("month")}>During month</button>
      </div>
      {viewMode !== "current" && (
        <input className={styles.monthInput} type="month" max={thisMonth} value={viewMonth}
          onChange={(e) => setViewMonth(e.target.value)} aria-label="Select month" />
      )}
      {viewMode !== "current" && viewMonth && (
        <span className={styles.viewNote}>
          {viewMode === "asof"
            ? "Cumulative progress up to the end of this month (read-only)."
            : "Only the progress recorded during this month (read-only)."}
        </span>
      )}
    </div>
  );

  if (gridZone) {
    return (
      <div>
        {viewControls}
        {filterBar}
        <ZoneGridView
          projectId={projectId}
          zoneId={gridZone.id}
          zoneName={gridZone.name}
          canManage={canManage}
          subzoneName={subzoneFilter}
          phaseName={phaseFilter}
          taskName={taskFilter}
          viewQuery={viewQuery}
          readOnly={viewMode !== "current"}
          onBack={() => setGridZone(null)}
          onChanged={reload}
        />
      </div>
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
            <input ref={scheduleFileRef} type="file" accept=".xlsx,.xlsm" hidden onChange={handleScheduleImport} />
            <Button size="sm" variant="secondary" disabled={scheduleImporting}
              onClick={() => scheduleFileRef.current?.click()}>
              {scheduleImporting ? "Importing…" : "Import Schedule"}
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

      {viewControls}
      {filterBar}

      <div className={styles.surface}>
        <StateView
          loading={loading}
          error={error}
          isEmpty={visibleRoots.length === 0}
          emptyTitle={zoneFilter ? "No matches" : "No structure yet"}
          emptyText={
            zoneFilter
              ? "Try a different filter."
              : (canManage ? "Add a phase, then zones and activities under it." : "Nothing has been set up yet.")
          }
          onRetry={reload}
        >
          <div key={`${zoneFilter}-${subzoneFilter}-${phaseFilter}`}>
            {visibleRoots.map((s) => (
              <ScopeNode
                key={s.id} scope={s} depth={0}
                projectId={projectId}
                childrenOf={childrenOf} progressOf={progressOf} activityCountOf={activityCountOf}
                canManage={canManage} canSubmit={canSubmit}
                visibleIds={visibleIds}
                onlyTaskName={taskFilter} viewQuery={viewQuery}
                onAddScope={(parentId, type) => setScopeModal({ parentId, scope: null, type })}
                onEditScope={(scope) => setScopeModal({ parentId: scope.parent, scope, type: scope.scope_type })}
                onDeleteScope={(scope) => del(`/projects/${projectId}/scopes/${scope.id}/`,
                  `Delete “${scope.name}” and everything under it?`)}
                onAddActivity={(scopeId) => setActivityModal({ scopeId, activity: null })}
                onEditActivity={(activity) => setActivityModal({ scopeId: activity.scope, activity })}
                onChanged={reload}
                onOpenGrid={openGrid}
                onOpenPhotos={(id, name) => setPhotosScope({ id, name })}
              />
            ))}
          </div>
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
