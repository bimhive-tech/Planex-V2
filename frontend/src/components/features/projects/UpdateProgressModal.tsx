"use client";

// Record a dated progress reading for an activity, with optional back-dating and
// optional photos (each with an optional caption). The reading is the source of
// truth behind the activity's current %; date-based reports read these entries.
// Photos are staged client-side so the user can remove a mistaken pick before
// saving; on save we create (or update) the entry, then upload staged photos.
// Recent entries are listed below; the author can edit/delete their own and
// managers can edit/delete any.
import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { useStagedPhotos } from "@/hooks/useStagedPhotos";
import type { Activity, ProgressEntry } from "@/types/project";
import { StagedPhotoPicker } from "./StagedPhotoPicker";
import styles from "./updateProgress.module.css";

interface Props {
  projectId: string;
  activity: Activity;
  onClose: () => void;
  onSaved: () => void;
}

// Today in the browser's local timezone (YYYY-MM-DD) — used as default and max.
const todayLocal = () => new Date().toLocaleDateString("en-CA");

export function UpdateProgressModal({ projectId, activity, onClose, onSaved }: Props) {
  const [value, setValue] = useState(activity.progress_percent);
  const [date, setDate] = useState(todayLocal());
  const [note, setNote] = useState("");
  const { photos, addFiles, removePhoto, setCaption, reset: resetPhotos } = useStagedPhotos();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const history = useFetch(
    () => api.get<ProgressEntry[]>(`/projects/${projectId}/activities/${activity.id}/progress/`),
    [projectId, activity.id],
  );
  const entries = history.data ?? [];

  function resetForm() {
    setValue(activity.progress_percent);
    setDate(todayLocal());
    setNote("");
    resetPhotos();
    setEditingId(null);
  }

  function startEdit(entry: ProgressEntry) {
    setEditingId(entry.id);
    setValue(entry.progress_percent);
    setDate(entry.date);
    setNote(entry.note);
    setError(null);
  }

  async function deleteEntry(entry: ProgressEntry) {
    if (!window.confirm("Delete this progress entry? This can't be undone.")) return;
    setError(null);
    try {
      await api.del(`/projects/${projectId}/progress-entries/${entry.id}/`);
      if (editingId === entry.id) resetForm();
      history.reload();
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete entry.");
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload = { progress_percent: Number(value), date, note };
      const entry = editingId
        ? await api.patch<{ id: string }>(`/projects/${projectId}/progress-entries/${editingId}/`, payload)
        : await api.post<{ id: string }>(`/projects/${projectId}/activities/${activity.id}/progress/`, payload);
      // Upload staged photos sequentially onto the saved entry.
      for (const p of photos) {
        const form = new FormData();
        form.append("image", p.file);
        form.append("caption", p.caption);
        await api.uploadApi(`/projects/${projectId}/progress-entries/${entry.id}/images/`, form);
      }
      resetForm();
      history.reload();
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save progress.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open title="Update progress" onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Close</Button>
          <Button type="submit" form="update-progress" disabled={busy}>
            {busy ? "Saving…" : editingId ? "Save changes" : "Save progress"}
          </Button>
        </>
      }>
      <form id="update-progress" onSubmit={save} className={styles.form}>
        <p className={styles.path}>{activity.name}</p>

        <div className={styles.row}>
          <Input label="Progress %" name="value" type="number" min="0" max="100" step="1" required autoFocus
            value={value} onChange={(e) => setValue(e.target.value)} />
          <Input label="Date" name="date" type="date" required
            max={todayLocal()} value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <p className="formHint">
          {editingId ? "Editing an earlier entry." : "Back-date if this progress happened earlier — you can’t pick a future date."}
        </p>

        <label className={styles.label} htmlFor="update-note">Note (optional)</label>
        <textarea id="update-note" className={styles.textarea} rows={2}
          value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything worth recording…" />

        <StagedPhotoPicker photos={photos} onAdd={addFiles} onRemove={removePhoto} onCaption={setCaption} />

        {editingId && (
          <button type="button" className={styles.cancelEdit} onClick={resetForm}>Cancel edit — record a new entry instead</button>
        )}

        {error && <p className="formError">{error}</p>}
      </form>

      {entries.length > 0 && (
        <div className={styles.history}>
          <span className={styles.label}>History</span>
          <ul className={styles.entryList}>
            {entries.map((en) => (
              <li key={en.id} className={`${styles.entry} ${editingId === en.id ? styles.entryActive : ""}`}>
                <span className={styles.entryDate}>{en.date}</span>
                <span className={`${styles.entryPct} tnum`}>{Math.round(Number(en.progress_percent))}%</span>
                <span className={styles.entryBy}>{en.recorded_by_name}</span>
                {en.can_edit && (
                  <span className={styles.entryActions}>
                    <button type="button" className={styles.entryBtn} aria-label="Edit entry" onClick={() => startEdit(en)}>
                      <Icon name="edit" size={13} />
                    </button>
                    <button type="button" className={`${styles.entryBtn} ${styles.danger}`} aria-label="Delete entry" onClick={() => deleteEntry(en)}>
                      <Icon name="trash" size={13} />
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
