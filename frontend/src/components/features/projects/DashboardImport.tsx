"use client";

// One upload for the whole dashboard workbook — cash flow, the progress curve
// the report's S-curve is drawn from, and the invoice extracts. The same file
// carries all three and used to need uploading once per panel (client ask,
// 2026-09-09). Backed by /projects/<id>/dashboard/import/.
import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import styles from "./finances.module.css";

/** What each part of the import reports back. Shapes differ per part, so this
 * only names the fields the summary line reads. */
interface DashboardImportResult {
  imported: {
    cashflow?: { months: number; first_month: string; last_month: string; curve_months?: number };
    invoices?: { periods: number; created: number; updated: number; skipped: number };
  };
  skipped: Record<string, string>;
}

interface Props {
  projectId: string;
  /** Refetch whatever is on screen — the import replaces the cash flow and
   * upserts the invoices, so both panels are stale afterwards. */
  onImported: () => void;
}

function summarise(r: DashboardImportResult): string {
  const parts: string[] = [];
  const cf = r.imported.cashflow;
  if (cf) {
    parts.push(`${cf.months} months of cash flow`);
    if (cf.curve_months) parts.push(`${cf.curve_months} progress-curve points`);
  }
  const inv = r.imported.invoices;
  if (inv) parts.push(`${inv.periods} invoice${inv.periods === 1 ? "" : "s"}`);
  return parts.length ? `Imported ${parts.join(", ")}.` : "Nothing to import.";
}

export function DashboardImport({ projectId, onImported }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // same file re-selectable
    if (!file) return;
    if (!window.confirm("Importing replaces this project's cash flow and progress curve, and updates its invoices. Continue?")) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api.uploadApi<DashboardImportResult>(
        `/projects/${projectId}/dashboard/import/`, form);
      // A workbook holding only some of the sheets still imports the rest, so
      // say which parts were not in it rather than reporting a clean success.
      const missing = Object.keys(result.skipped ?? {});
      setMessage(summarise(result) + (missing.length ? ` No ${missing.join(" or ")} sheet in this workbook.` : ""));
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Dashboard import failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.importBar}>
      <input ref={fileRef} type="file" accept=".xlsx,.xlsm" hidden onChange={handleFile} />
      <Button size="sm" variant="secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
        {busy ? "Importing…" : "Import dashboard"}
      </Button>
      <span className={styles.importHint}>
        One upload: cash flow, progress curve and invoices.
      </span>
      {message && <p className={styles.importMsg}>{message}</p>}
      {error && <p className="formError">{error}</p>}
    </div>
  );
}
