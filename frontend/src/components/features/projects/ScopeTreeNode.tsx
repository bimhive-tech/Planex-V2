"use client";

// One row (+ its children) in the Schedule tab's nested tree: Phase → Zone →
// Building → Area → Activity. Recursive; lazily loads activities under leaves.
import { useState, type CSSProperties } from "react";

import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import type { Activity, Scope } from "@/types/project";
import { ScopeActivities } from "./ScopeActivities";
import styles from "./scheduleTree.module.css";

const NEXT_TYPE: Record<string, string> = { phase: "zone", zone: "building", building: "area", area: "area" };

export interface ScopeNodeProps {
  scope: Scope;
  depth: number;
  projectId: string;
  childrenOf: Map<string | null, Scope[]>;
  progressOf: (scopeId: string) => number;
  activityCountOf: Record<string, number>;
  canManage: boolean;
  canSubmit: boolean;
  // null = no filter active. Otherwise only children whose id is in the set
  // are rendered (the rest of the active Zone/Subzone/Phase filter's siblings).
  visibleIds: Set<string> | null;
  // Active Task filter (by name) — passed through to ScopeActivities.
  onlyTaskName: string;
  // As-of / month view mode query (?mode=…&as_of=…), "" for the current view.
  viewQuery: string;
  onAddScope: (parentId: string, type: string) => void;
  onEditScope: (scope: Scope) => void;
  onDeleteScope: (scope: Scope) => void;
  onAddActivity: (scopeId: string) => void;
  onEditActivity: (activity: Activity) => void;
  onChanged: () => void;
  onOpenGrid: (id: string, name: string) => void;
  onOpenPhotos: (id: string, name: string) => void;
}

export function ScopeNode(props: ScopeNodeProps) {
  const { scope, depth, childrenOf, progressOf, activityCountOf, canManage, visibleIds } = props;
  const childScopes = (childrenOf.get(scope.id) ?? []).filter((c) => !visibleIds || visibleIds.has(c.id));
  const activityCount = activityCountOf[scope.id] ?? 0;
  // Collapse nodes with many children/tasks by default — unless a Zone/Subzone/
  // Phase filter is active, in which case the tree is already pruned to the
  // selected branch, so always reveal it.
  const [open, setOpen] = useState(visibleIds ? true : childScopes.length <= 25 && activityCount <= 25);
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
        <button className={styles.gridBtn} title="Progress photos" aria-label="Progress photos"
          onClick={() => props.onOpenPhotos(scope.id, scope.name)}>
          <Icon name="image" size={14} />
          <span>Photos</span>
        </button>
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
              onlyName={props.onlyTaskName} viewQuery={props.viewQuery}
              onEdit={props.onEditActivity} onChanged={props.onChanged}
            />
          )}
        </>
      )}
    </div>
  );
}
