"use client";

// Field progress submission: an engineer proposes a new progress value for a
// task, with optional supporting photos. It enters the review/approval chain —
// it does NOT change the official value until accepted.
import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useStagedPhotos } from "@/hooks/useStagedPhotos";
import type { Activity } from "@/types/project";
import { StagedPhotoPicker } from "./StagedPhotoPicker";
import styles from "./updateProgress.module.css";

interface Props {
  projectId: string;
  activity: Activity;
  onClose: () => void;
  onSubmitted: () => void;
}

export function SubmitProgressModal({ projectId, activity, onClose, onSubmitted }: Props) {
  const [value, setValue] = useState(activity.progress_percent);
  const [note, setNote] = useState("");
  const { photos, addFiles, removePhoto, setCaption } = useStagedPhotos();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sub = await api.post<{ id: string }>(`/projects/${projectId}/submissions/`, {
        activity: activity.id, submitted_progress: Number(value), note,
      });
      // Attach any staged photos onto the submission just created.
      for (const p of photos) {
        const form = new FormData();
        form.append("image", p.file);
        form.append("caption", p.caption);
        await api.uploadApi(`/projects/${projectId}/submissions/${sub.id}/images/`, form);
      }
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

        <StagedPhotoPicker photos={photos} onAdd={addFiles} onRemove={removePhoto} onCaption={setCaption}
          label="Supporting photos (optional)" />

        <p className="formHint">This goes to review &amp; approval — the official value changes only once accepted.</p>
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
