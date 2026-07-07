"use client";

// Excel-style grid for one zone: subzones across the columns, tasks down the
// rows (grouped by phase), each cell an editable progress value. Cells save on
// blur; the sticky first column keeps task names visible while scrolling.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { GridRow, ZoneGrid } from "@/types/project";
import styles from "./zoneGrid.module.css";

interface Props {
  projectId: string;
  zoneId: string;
  zoneName: string;
  canManage: boolean;
  // Active Subzone/Phase/Task filter (by name) carried over from the tree's
  // filter bar — narrows the columns/rows shown for this same zone.
  subzoneName?: string;
  phaseName?: string;
  taskName?: string;
  viewQuery?: string; // as-of / month view mode (?mode=…&as_of=…), "" for current
  readOnly?: boolean; // as-of / month views are historical — no cell editing
  onBack: () => void;
  onChanged: () => void;
}

export function ZoneGridView({
  projectId, zoneId, zoneName, canManage, subzoneName, phaseName, taskName,
  viewQuery = "", readOnly = false, onBack, onChanged,
}: Props) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ZoneGrid>(`/projects/${projectId}/zones/${zoneId}/grid/${viewQuery}`),
    [projectId, zoneId, viewQuery],
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  // Keep each kept column's original index so a row's `cells` array (positionally
  // aligned to the unfiltered subzone list) still lines up after filtering.
  const columns = (data?.subzones ?? [])
    .map((sz, col) => ({ ...sz, col }))
    .filter((sz) => !subzoneName || sz.name === subzoneName);
  const rows = (data?.rows ?? []).filter(
    (r) => (!phaseName || r.phase === phaseName) && (!taskName || r.name === taskName),
  );
  const filtered = !!(subzoneName || phaseName || taskName);

  async function saveCell(activityId: string, value: string, current: string) {
    const v = Math.max(0, Math.min(100, Number(value)));
    if (Number.isNaN(v) || String(v) === current) return;
    setSaveError(null);
    try {
      await api.patch(`/projects/${projectId}/activities/${activityId}/`, { progress_percent: v });
      onChanged(); // refresh roll-ups (donut/tree) upstream
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save cell.");
    }
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <Button size="sm" variant="secondary" leadingIcon={<Icon name="chevronDown" size={15} />} onClick={onBack}>
          Back to tree
        </Button>
        <span className={styles.title}>{zoneName}</span>
        <span className={styles.muted}>
          {data ? `${columns.length} subzones · ${rows.length} tasks` : ""}
        </span>
      </div>

      {saveError && <p className="formError">{saveError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={!!data && rows.length === 0}
        emptyTitle={filtered ? "No matches" : "No tasks in this zone"}
        emptyText={filtered ? "Try a different filter." : undefined}
        onRetry={reload}
      >
        {data && (
          <div className={styles.scroll}>
            <table className={styles.grid}>
              <thead>
                <tr>
                  <th className={`${styles.corner} ${styles.sticky}`}>Task</th>
                  <th className={styles.wHead}>W</th>
                  {columns.map((sz) => (
                    <th key={sz.id} className={styles.colHead} title={sz.name}>{sz.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {renderRows(rows, columns, canManage && !readOnly, saveCell)}
              </tbody>
            </table>
          </div>
        )}
      </StateView>
    </div>
  );
}

function renderRows(
  rows: GridRow[],
  columns: { col: number }[],
  canManage: boolean,
  saveCell: (id: string, v: string, cur: string) => void,
) {
  const out: React.ReactNode[] = [];
  let lastPhase: string | null = null;
  for (const row of rows) {
    if (row.phase && row.phase !== lastPhase) {
      lastPhase = row.phase;
      out.push(
        <tr key={`phase-${row.row_index}`}>
          <td className={`${styles.phaseRow} ${styles.sticky}`} colSpan={columns.length + 2}>{row.phase}</td>
        </tr>,
      );
    }
    out.push(
      <tr key={row.row_index} className={styles.taskRow}>
        <td className={`${styles.taskName} ${styles.sticky}`} title={row.name}>{row.name}</td>
        <td className={styles.weight}>{row.weight}</td>
        {columns.map(({ col }) => {
          const cell = row.cells[col];
          return cell ? (
            <td key={col} className={styles.cell}>
              {canManage ? (
                <input
                  className={styles.cellInput}
                  type="number" min="0" max="100"
                  defaultValue={cell.progress}
                  onBlur={(e) => saveCell(cell.id, e.target.value, cell.progress)}
                />
              ) : (
                <span className={styles.cellValue}>{Math.round(Number(cell.progress))}</span>
              )}
            </td>
          ) : (
            <td key={col} className={`${styles.cell} ${styles.empty}`} />
          );
        })}
      </tr>,
    );
  }
  return out;
}
