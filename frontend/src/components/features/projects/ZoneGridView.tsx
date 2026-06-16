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
  onBack: () => void;
  onChanged: () => void;
}

export function ZoneGridView({ projectId, zoneId, zoneName, canManage, onBack, onChanged }: Props) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ZoneGrid>(`/projects/${projectId}/zones/${zoneId}/grid/`),
    [projectId, zoneId],
  );
  const [saveError, setSaveError] = useState<string | null>(null);

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
          {data ? `${data.subzones.length} subzones · ${data.rows.length} tasks` : ""}
        </span>
      </div>

      {saveError && <p className="formError">{saveError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={!!data && data.rows.length === 0}
        emptyTitle="No tasks in this zone"
        onRetry={reload}
      >
        {data && (
          <div className={styles.scroll}>
            <table className={styles.grid}>
              <thead>
                <tr>
                  <th className={`${styles.corner} ${styles.sticky}`}>Task</th>
                  <th className={styles.wHead}>W</th>
                  {data.subzones.map((sz) => (
                    <th key={sz.id} className={styles.colHead} title={sz.name}>{sz.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {renderRows(data.rows, data.subzones.length, canManage, saveCell)}
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
  colCount: number,
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
          <td className={`${styles.phaseRow} ${styles.sticky}`} colSpan={colCount + 2}>{row.phase}</td>
        </tr>,
      );
    }
    out.push(
      <tr key={row.row_index} className={styles.taskRow}>
        <td className={`${styles.taskName} ${styles.sticky}`} title={row.name}>{row.name}</td>
        <td className={styles.weight}>{row.weight}</td>
        {row.cells.map((cell, i) =>
          cell ? (
            <td key={i} className={styles.cell}>
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
            <td key={i} className={`${styles.cell} ${styles.empty}`} />
          ),
        )}
      </tr>,
    );
  }
  return out;
}
