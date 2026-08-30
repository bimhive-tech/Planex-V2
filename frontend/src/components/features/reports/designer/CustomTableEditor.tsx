"use client";

// Spreadsheet-style editor for a table element's `source: "custom"` data —
// rendered directly on the canvas (ElementPreview's TablePreview) so a custom
// table's rows/columns/cells are all edited right on the page, not in the
// Properties panel. Kept as one rectangular grid while editing (row 0 is
// always the header) so add/remove/paste stay simple, then split back into
// `{ columns, rows }` — the shape apps/reports/pdf_canvas.py's resolve_table
// reads directly off props.custom_data — on every change. Every interactive
// control stops pointerdown propagation — without it, a click here would
// also bubble up to CanvasElementView's onStartMove and drag the whole
// table element instead of (or as well as) hitting the control.
import { Button } from "@/components/ui/Button";
import type { CustomTableData } from "@/lib/reportLayout";
import styles from "./designer.module.css";

const MIN_COLS = 1;
const MAX_ROWS = 200;
const MAX_COLS = 30;

function toGrid(data: CustomTableData | undefined): string[][] {
  const columns = data?.columns?.length ? data.columns : ["Column 1", "Column 2"];
  const rows = data?.rows?.length ? data.rows : [["", ""]];
  return [columns, ...rows.map((r) => padTo(r, columns.length))];
}

function padTo(row: string[], width: number): string[] {
  const next = row.slice(0, width);
  while (next.length < width) next.push("");
  return next;
}

function fromGrid(grid: string[][]): CustomTableData {
  const [columns, ...rows] = grid;
  return { columns, rows };
}

/** Excel puts a plain tab/newline-separated grid on the clipboard when you
 * copy cells — this is the whole "paste from Excel" mechanism, no upload or
 * backend parsing needed. */
function splitClipboard(text: string): string[][] {
  const lines = text.replace(/\r/g, "").split("\n");
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines.map((line) => line.split("\t"));
}

interface Props {
  data: CustomTableData | undefined;
  onChange: (data: CustomTableData) => void;
}

export function CustomTableEditor({ data, onChange }: Props) {
  const grid = toGrid(data);

  function setCell(r: number, c: number, value: string) {
    onChange(fromGrid(grid.map((row, i) => (i === r ? row.map((cell, j) => (j === c ? value : cell)) : row))));
  }

  function addRow() {
    if (grid.length - 1 >= MAX_ROWS) return;
    onChange(fromGrid([...grid, grid[0].map(() => "")]));
  }

  function removeRow(r: number) {
    if (grid.length <= 2) return; // header + at least one body row
    onChange(fromGrid(grid.filter((_, i) => i !== r)));
  }

  function addColumn() {
    if (grid[0].length >= MAX_COLS) return;
    const label = `Column ${grid[0].length + 1}`;
    onChange(fromGrid(grid.map((row, i) => [...row, i === 0 ? label : ""])));
  }

  function removeColumn(c: number) {
    if (grid[0].length <= MIN_COLS) return;
    onChange(fromGrid(grid.map((row) => row.filter((_, j) => j !== c))));
  }

  function pasteAt(r: number, c: number, text: string) {
    const pasted = splitClipboard(text);
    if (!pasted.length) return;
    const width = Math.min(MAX_COLS, Math.max(grid[0].length, c + Math.max(...pasted.map((row) => row.length))));
    const height = Math.min(MAX_ROWS + 1, Math.max(grid.length, r + pasted.length));
    const next: string[][] = [];
    for (let i = 0; i < height; i++) {
      const existing = grid[i] ?? [];
      const row: string[] = [];
      for (let j = 0; j < width; j++) row[j] = existing[j] ?? (i === 0 ? `Column ${j + 1}` : "");
      next.push(row);
    }
    pasted.forEach((row, i) => {
      if (r + i >= height) return;
      row.forEach((cell, j) => {
        if (c + j < width) next[r + i][c + j] = cell;
      });
    });
    onChange(fromGrid(next));
  }

  return (
    <div className={styles.customTableEditor}>
      <p className={styles.panelHint}>
        Edit cells directly, or click a cell and paste (Ctrl+V) to bring in data copied from Excel.
      </p>
      <div className={styles.customTableGrid}>
        <table>
          <tbody>
            {grid.map((row, r) => (
              <tr key={r}>
                <td className={styles.customTableRowHandle}>
                  {r > 0 && (
                    <button
                      type="button"
                      onClick={() => removeRow(r)}
                      onPointerDown={(e) => e.stopPropagation()}
                      aria-label={`Remove row ${r}`}
                    >
                      ×
                    </button>
                  )}
                </td>
                {row.map((cell, c) => (
                  <td key={c} data-header={r === 0 ? "on" : undefined}>
                    <div className={styles.customTableCell}>
                      <input
                        value={cell}
                        onChange={(e) => setCell(r, c, e.target.value)}
                        onPaste={(e) => {
                          e.preventDefault();
                          pasteAt(r, c, e.clipboardData.getData("text/plain"));
                        }}
                        onPointerDown={(e) => e.stopPropagation()}
                      />
                      {r === 0 && grid[0].length > MIN_COLS && (
                        <button
                          type="button"
                          className={styles.customTableColRemove}
                          onClick={() => removeColumn(c)}
                          onPointerDown={(e) => e.stopPropagation()}
                          aria-label={`Remove column ${c + 1}`}
                        >
                          ×
                        </button>
                      )}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.customTableActions} onPointerDown={(e) => e.stopPropagation()}>
        <Button type="button" variant="secondary" size="sm" onClick={addRow}>Add row</Button>
        <Button type="button" variant="secondary" size="sm" onClick={addColumn}>Add column</Button>
      </div>
    </div>
  );
}
