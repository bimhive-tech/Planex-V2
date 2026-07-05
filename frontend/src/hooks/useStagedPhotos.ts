"use client";

// Client-side staging for photos picked before the parent record exists yet
// (e.g. a new progress entry or submission): add/remove/caption locally, then
// upload each once the parent has been saved. Revokes preview URLs on cleanup.
import { useEffect, useState } from "react";

export interface StagedPhoto {
  id: string; // local key only
  file: File;
  caption: string;
  preview: string;
}

export function useStagedPhotos() {
  const [photos, setPhotos] = useState<StagedPhoto[]>([]);

  useEffect(() => () => photos.forEach((p) => URL.revokeObjectURL(p.preview)), [photos]);

  function addFiles(files: FileList | null) {
    if (!files) return;
    const next = Array.from(files).map((file) => ({
      id: crypto.randomUUID(), file, caption: "", preview: URL.createObjectURL(file),
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

  function reset() {
    photos.forEach((p) => URL.revokeObjectURL(p.preview));
    setPhotos([]);
  }

  return { photos, addFiles, removePhoto, setCaption, reset };
}
