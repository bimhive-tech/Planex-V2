"use client";

// Monthly cash-flow grid: the user types a planned and an actual amount per
// month; we store them as-is (no calculation) and the report charts them. Save
// does an atomic bulk-replace of the whole table.
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import styles from "./finances.module.css";

interface Row { month: string; planned: string; actual: string }
interface CashFlowData { entries: { id: string; month: string; planned: string; actual: string }[]; currency: string }

const monthLabel = (iso: string) =>
  new Date(iso).toLocaleDateString("en", { year: "numeric", month: "short", timeZone: "UTC" });

export function CashFlowPanel({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<CashFlowData>(`/projects/${projectId}/cashflow/`),
    [projectId],
  );
  const [rows, setRows] = useState<Row[]>([]);
  const [newMonth, setNewMonth] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (data) {
      setRows(data.entries.map((e) => ({ month: e.month, planned: e.planned, actual: e.actual })));
      setDirty(false);
    }
  }, [data]);

  const currency = data?.currency ?? "";
  const totals = useMemo(() => rows.reduce(
    (acc, r) => ({ planned: acc.planned + (Number(r.planned) || 0), actual: acc.actual + (Number(r.actual) || 0) }),
    { planned: 0, actual: 0 }), [rows]);

  function setCell(i: number, key: "planned" | "actual", value: string) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)));
    setDirty(true);
  }
  function removeRow(i: number) {
    setRows((rs) => rs.filter((_, idx) => idx !== i));
    setDirty(true);
  }
  function addRow() {
    if (!newMonth) return;
    const month = `${newMonth}-01`;
    if (rows.some((r) => r.month === month)) { setActionError("That month is already in the table."); return; }
    setActionError(null);
    setRows((rs) => [...rs, { month, planned: "0", actual: "0" }].sort((a, b) => a.month.localeCompare(b.month)));
    setNewMonth("");
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    setActionError(null);
    try {
      await api.put(`/projects/${projectId}/cashflow/`,
        rows.map((r) => ({ month: r.month, planned: Number(r.planned) || 0, actual: Number(r.actual) || 0 })));
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't save cash flow.");
    } finally {
      setSaving(false);
    }
  }

  // Import replaces the whole table from an Excel sheet (months across a row with
  // planned/actual rows, or a Month/Planned/Actual table) — hence the confirm.
  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    if (rows.length && !window.confirm("Importing replaces the current cash-flow table. Continue?")) return;
    setImporting(true);
    setActionError(null);
    setImportMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.uploadApi<{ months: number; first_month: string; last_month: string }>(
        `/projects/${projectId}/cashflow/import/`, form);
      setImportMsg(`Imported ${r.months} months (${monthLabel(r.first_month)} – ${monthLabel(r.last_month)}).`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Cash-flow import failed.");
    } finally {
      setImporting(false);
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Cash Flow {currency && <span className={styles.muted}>({currency})</span>}</h2>
        {canManage && (
          <div className={styles.headActions}>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm" hidden onChange={handleImport} />
            <Button size="sm" variant="secondary" disabled={importing}
              onClick={() => fileRef.current?.click()}>
              {importing ? "Importing…" : "Import Excel"}
            </Button>
            {dirty && (
              <Button size="sm" disabled={saving} onClick={save}>{saving ? "Saving…" : "Save changes"}</Button>
            )}
          </div>
        )}
      </header>

      {importMsg && <p className={styles.importMsg}>{importMsg}</p>}
      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={rows.length === 0 && !canManage}
        emptyTitle="No cash-flow data"
        emptyText="Monthly planned vs actual amounts appear here and in the report."
        onRetry={reload}
      >
        <div className={styles.tableWrap}>
          <table className={styles.grid}>
            <thead>
              <tr><th>Month</th><th>Planned</th><th>Actual</th>{canManage && <th aria-label="actions" />}</tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.month}>
                  <td>{monthLabel(r.month)}</td>
                  <td>
                    {canManage
                      ? <input className={styles.cell} type="number" step="0.01" value={r.planned} onChange={(e) => setCell(i, "planned", e.target.value)} />
                      : Number(r.planned).toLocaleString()}
                  </td>
                  <td>
                    {canManage
                      ? <input className={styles.cell} type="number" step="0.01" value={r.actual} onChange={(e) => setCell(i, "actual", e.target.value)} />
                      : Number(r.actual).toLocaleString()}
                  </td>
                  {canManage && (
                    <td>
                      <button className={styles.iconBtn} aria-label="Remove month" onClick={() => removeRow(i)}>
                        <Icon name="trash" size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Total</td>
                <td>{totals.planned.toLocaleString()}</td>
                <td>{totals.actual.toLocaleString()}</td>
                {canManage && <td />}
              </tr>
            </tfoot>
          </table>
        </div>

        {canManage && (
          <div className={styles.addRow}>
            <input className={styles.monthInput} type="month" value={newMonth} onChange={(e) => setNewMonth(e.target.value)} />
            <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />} onClick={addRow} disabled={!newMonth}>
              Add month
            </Button>
          </div>
        )}
      </StateView>
    </section>
  );
}
