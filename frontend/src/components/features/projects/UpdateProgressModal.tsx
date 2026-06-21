"use client";

// Record a dated progress reading for an activity, with optional back-dating and
// optional photos (each with an optional caption). The reading is the source of
// truth behind the activity's current %; date-based reports read these entries.
// Photos are staged client-side so the user can remove a mistaken pick before
// saving; on save we create the entry, then upload each staged photo to it.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import type { Activity } from "@/types/project";
import styles from "./updateProgress.module.css";

interface Props {
  projectId: string;
  activity: Activity;
  onClose: () => void;
  onSaved: () => void;
}

interface StagedPhoto {
  id: string; // local key only
  file: File;
  caption: string;
  preview: string;
}

interface CreatedEntry {
  id: string;
}

// Today in the browser's local timezone (YYYY-MM-DD) — used as default and max.
const todayLocal = () => new Date().toLocaleDateString("en-CA");

export function UpdateProgressModal({ projectId, activity, onClose, onSaved }: Props) {
  const [value, setValue] = useState(activity.progress_percent);
  const [date, setDate] = useState(todayLocal());
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState<StagedPhoto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Revoke object URLs on unmount to avoid leaking blobs.
  useEffect(() => () => photos.forEach((p) => URL.revokeObjectURL(p.preview)), [photos]);

  function addFiles(files: FileList | null) {
    if (!files) return;
    const next = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      file,
      caption: "",
      preview: URL.createObjectURL(file),
    }));
    setPhotos((prev) => [...prev, ...next]);
  }

  function removePhoto(id: string) {
    setPhotos((prev) => {
      const gone = prev.find((p) => p.id === id);
      if (gone) URL.revokeObjectURL(gone.preview);
      return prev.filter((p) => p.id !== id);
    });
  }

  function setCaption(id: string, caption: string) {
    setPhotos((prev) => prev.map((p) => (p.id === id ? { ...p, caption } : p)));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const entry = await api.post<CreatedEntry>(
        `/projects/${projectId}/activities/${activity.id}/progress/`,
        { progress_percent: Number(value), date, note },
      );
      // Upload staged photos sequentially onto the new entry.
      for (const p of photos) {
        const form = new FormData();
        form.append("image", p.file);
        form.append("caption", p.caption);
        await api.uploadApi(`/projects/${projectId}/progress-entries/${entry.id}/images/`, form);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save progress.");
      setBusy(false);
    }
  }

  return (
    <Modal open title="Update progress" onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="update-progress" disabled={busy}>{busy ? "Saving…" : "Save progress"}</Button>
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
        <p className="formHint">Back-date if this progress happened earlier — you can&apos;t pick a future date.</p>

        <label className={styles.label} htmlFor="update-note">Note (optional)</label>
        <textarea id="update-note" className={styles.textarea} rows={2}
          value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything worth recording…" />

        <div className={styles.photosHead}>
          <span className={styles.label}>Photos (optional)</span>
          <label className={styles.addPhoto}>
            <Icon name="image" size={15} /> Add photos
            <input type="file" accept="image/png,image/jpeg,image/webp" multiple
              onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          </label>
        </div>

        {photos.length > 0 && (
          <ul className={styles.photoList}>
            {photos.map((p) => (
              <li key={p.id} className={styles.photoItem}>
                {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview, not an R2 asset */}
                <img className={styles.thumb} src={p.preview} alt="" />
                <input className={styles.captionInput} value={p.caption} placeholder="Caption (optional)"
                  onChange={(e) => setCaption(p.id, e.target.value)} />
                <button type="button" className={styles.removePhoto} aria-label="Remove photo" onClick={() => removePhoto(p.id)}>
                  <Icon name="trash" size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}

        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
