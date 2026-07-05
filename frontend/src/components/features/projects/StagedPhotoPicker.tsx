"use client";

// "Add photos" trigger + thumbnail list (caption + remove) for photos staged
// before the parent record is saved. Shared by the Update-progress and
// Submit-progress modals so the picker UI only exists once.
import { Icon } from "@/components/ui/Icon";
import type { StagedPhoto } from "@/hooks/useStagedPhotos";
import styles from "./stagedPhotoPicker.module.css";

interface Props {
  photos: StagedPhoto[];
  onAdd: (files: FileList | null) => void;
  onRemove: (id: string) => void;
  onCaption: (id: string, caption: string) => void;
  label?: string;
}

export function StagedPhotoPicker({ photos, onAdd, onRemove, onCaption, label = "Photos (optional)" }: Props) {
  return (
    <div>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        <label className={styles.addPhoto}>
          <Icon name="image" size={15} /> Add photos
          <input type="file" accept="image/png,image/jpeg,image/webp" multiple
            onChange={(e) => { onAdd(e.target.files); e.target.value = ""; }} />
        </label>
      </div>

      {photos.length > 0 && (
        <ul className={styles.list}>
          {photos.map((p) => (
            <li key={p.id} className={styles.item}>
              {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview, not an R2 asset */}
              <img className={styles.thumb} src={p.preview} alt="" />
              <input className={styles.captionInput} value={p.caption} placeholder="Caption (optional)"
                onChange={(e) => onCaption(p.id, e.target.value)} />
              <button type="button" className={styles.remove} aria-label="Remove photo" onClick={() => onRemove(p.id)}>
                <Icon name="trash" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
