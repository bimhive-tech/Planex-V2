"use client";

// Flat, searchable view of one scope level (phase/zone/building/area) for the
// Schedule tab's filter — same rows as the tree, minus the nesting, plus a
// breadcrumb back to where each one lives.
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import type { Scope } from "@/types/project";
import { scopePath } from "./scopeBreadcrumb";
import styles from "./scheduleTree.module.css";

interface Props {
  scopes: Scope[];
  scopeIdsWithChildren: Set<string>;
  scopeById: Map<string, Scope>;
  progressOf: (scopeId: string) => number;
  canManage: boolean;
  onEditScope: (scope: Scope) => void;
  onDeleteScope: (scope: Scope) => void;
  onOpenGrid: (id: string, name: string) => void;
  onOpenPhotos: (id: string, name: string) => void;
}

export function ScheduleFlatList({
  scopes, scopeIdsWithChildren, scopeById, progressOf, canManage,
  onEditScope, onDeleteScope, onOpenGrid, onOpenPhotos,
}: Props) {
  if (scopes.length === 0) {
    return <p className={styles.emptyFlat}>No matches.</p>;
  }

  return (
    <>
      {scopes.map((scope) => {
        const pct = progressOf(scope.id);
        const breadcrumb = scopePath(scope.parent, scopeById);
        return (
          <div key={scope.id} className={styles.scopeRow}>
            <Badge tone="info">{scope.scope_type_display}</Badge>
            <div className={styles.flatNameBlock}>
              {breadcrumb && <span className={styles.breadcrumb}>{breadcrumb}</span>}
              <span className={styles.scopeName}>{scope.name}</span>
            </div>
            <div className={styles.bar}><span className={styles.barFill} style={{ ["--pct" as string]: `${pct}%` }} /></div>
            <span className={`${styles.pct} tnum`}>{pct}%</span>
            {scope.scope_type === "zone" && scopeIdsWithChildren.has(scope.id) && (
              <button className={styles.gridBtn} title="Open Excel grid" aria-label="Open Excel grid"
                onClick={() => onOpenGrid(scope.id, scope.name)}>
                <Icon name="dashboard" size={14} />
                <span>Grid</span>
              </button>
            )}
            <button className={styles.gridBtn} title="Progress photos" aria-label="Progress photos"
              onClick={() => onOpenPhotos(scope.id, scope.name)}>
              <Icon name="image" size={14} />
              <span>Photos</span>
            </button>
            {canManage && (
              <div className={styles.actions}>
                <button className={styles.actionBtn} title="Rename" aria-label="Rename"
                  onClick={() => onEditScope(scope)}>
                  <Icon name="edit" size={14} />
                </button>
                <button className={`${styles.actionBtn} ${styles.danger}`} title="Delete" aria-label="Delete"
                  onClick={() => onDeleteScope(scope)}>
                  <Icon name="trash" size={14} />
                </button>
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}
