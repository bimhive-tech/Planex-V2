"use client";

// The one way to import a file into a project (register E1): what it is — a
// P6 schedule or the dashboard workbook — the date its data is as of, and the
// file. Opened from the Import button beside Export P6, and from the Finances
// tab's Imports view, so both files come in through the same questions.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { DASHBOARD_PART_NAMES } from "@/lib/dashboardImport";
import {
  dashboardSummary, IMPORT_KIND_LABELS, scheduleSummary,
  type DashboardImportResult, type ProjectImportKind, type ScheduleImportResult,
} from "@/lib/projectImport";
import styles from "./projectImport.module.css";

interface Props {
  projectId: string;
  /** The kinds this user may import, in the order offered; the first is preselected. */
  kinds: ProjectImportKind[];
  onClose: () => void;
  /** Called after a successful import, so whatever shows that data can reload. */
  onImported: (kind: ProjectImportKind) => void;
}

export function ProjectImportDialog({ projectId, kinds, onClose, onImported }: Props) {
  const [kind, setKind] = useState<ProjectImportKind>(kinds[0]);
  const [date, setDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Choose the file to import."); return; }
    setBusy(true);
    setError(null);
    try {
      if (kind === "schedule") {
        // The schedule upload goes through the long-running /upload route, not the API proxy.
        const r = await api.upload<ScheduleImportResult>(
          `/upload/import/${projectId}`, file, "file", date ? { date } : undefined);
        setDone(scheduleSummary(r));
      } else {
        const form = new FormData();
        form.append("file", file);
        if (date) form.append("date", date);
        const r = await api.uploadApi<DashboardImportResult>(`/projects/${projectId}/dashboard/import/`, form);
        setDone(dashboardSummary(r, DASHBOARD_PART_NAMES));
      }
      onImported(kind);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  }

  const footer = done
    ? <Button type="button" onClick={onClose}>Done</Button>
    : (
      <>
        <Button variant="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" form="project-import-form" disabled={busy || !file}>
          {busy ? "Importing…" : "Import"}
        </Button>
      </>
    );

  return (
    <Modal open title="Import" onClose={onClose} footer={footer}>
      {done ? (
        <p className={styles.result} role="status">{done}</p>
      ) : (
        <form id="project-import-form" onSubmit={submit} className={styles.form}>
          {kinds.length > 1 && (
            <fieldset className={styles.kinds}>
              <legend className={styles.legend}>What are you importing?</legend>
              {kinds.map((k) => (
                <label key={k} className={`${styles.kind} ${kind === k ? styles.kindOn : ""}`}>
                  <input type="radio" name="import-kind" value={k} checked={kind === k}
                    onChange={() => setKind(k)} />
                  <span className={styles.kindText}>
                    <strong>{IMPORT_KIND_LABELS[k].title}</strong>
                    <span>{IMPORT_KIND_LABELS[k].hint}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          {kinds.length === 1 && <p className={styles.hint}>{IMPORT_KIND_LABELS[kind].hint}</p>}
          <div>
            <Input label="Data as of" name="import-date" type="date" value={date}
              onChange={(e) => setDate(e.target.value)} />
            <p className={styles.hint}>
              The date this file&apos;s figures describe. Leave empty to take it from the file name
              {kind === "schedule" ? ", or today" : ""}.
            </p>
          </div>
          <Input label="File" name="import-file" type="file" accept=".xlsx,.xlsm" required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {error && <p className="formError">{error}</p>}
        </form>
      )}
    </Modal>
  );
}
