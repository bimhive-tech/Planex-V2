"use client";

// Field progress submission: an engineer proposes a new progress value for a
// task. It enters the review/approval chain (it does NOT change the official
// value until accepted).
import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import type { Activity } from "@/types/project";
import styles from "./approvals.module.css";

interface Props {
  projectId: string;
  activity: Activity;
  onClose: () => void;
  onSubmitted: () => void;
}

export function SubmitProgressModal({ projectId, activity, onClose, onSubmitted }: Props) {
  const [value, setValue] = useState(activity.progress_percent);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/projects/${projectId}/submissions/`, {
        activity: activity.id, submitted_progress: Number(value), note,
      });
      onSubmitted();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't submit.");
      setBusy(false);
    }
  }

  return (
    <Modal open title="Submit progress" onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="submit-progress" disabled={busy}>{busy ? "Submitting…" : "Submit for review"}</Button>
        </>
      }>
      <form id="submit-progress" onSubmit={submit} className={styles.form}>
        <p className={styles.path}>{activity.name}</p>
        <Input label="Progress %" name="value" type="number" min="0" max="100" step="1" required autoFocus
          value={value} onChange={(e) => setValue(e.target.value)} />
        <label className={styles.label} htmlFor="submit-note">Note (optional)</label>
        <textarea id="submit-note" className={styles.textarea} rows={2}
          value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything the reviewer should know…" />
        <p className="formHint">This goes to review &amp; approval — the official value changes only once accepted.</p>
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
