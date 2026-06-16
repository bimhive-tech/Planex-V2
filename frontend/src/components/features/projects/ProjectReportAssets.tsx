"use client";

// Report image assets: logos, cover image, and site photos used by generated PDFs.
import { useState } from "react";
import Image from "next/image";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ProjectImage, ProjectImageType } from "@/types/project";
import styles from "./projectOverview.module.css";

const IMAGE_TYPES: { value: ProjectImageType; label: string }[] = [
  { value: "site_photo", label: "Site photo" },
  { value: "cover", label: "Cover image" },
  { value: "logo_left", label: "Left logo" },
  { value: "logo_right", label: "Right logo" },
];

export function ProjectReportAssets({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const [imageType, setImageType] = useState<ProjectImageType>("site_photo");
  const [caption, setCaption] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectImage[]>(`/projects/${projectId}/images/`),
    [projectId],
  );
  const images = data ?? [];

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setActionError(null);
    try {
      const form = new FormData();
      form.append("image", file);
      form.append("image_type", imageType);
      form.append("caption", caption);
      await api.uploadApi<ProjectImage>(`/projects/${projectId}/images/`, form);
      setFile(null);
      setCaption("");
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't upload image.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(image: ProjectImage) {
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/images/${image.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete image.");
    }
  }

  return (
    <section className={`${styles.card} ${styles.full}`}>
      <header className={styles.cardHead}>
        <h2 className={styles.cardTitle}>Report Assets</h2>
        <p className={styles.cardSub}>Logos, cover image, and site photos rendered in generated PDFs.</p>
      </header>

      {canManage && (
        <form className={styles.assetForm} onSubmit={upload}>
          <select className={styles.assetSelect} value={imageType} onChange={(e) => setImageType(e.target.value as ProjectImageType)}>
            {IMAGE_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
          </select>
          <input className={styles.assetInput} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Caption" />
          <input className={styles.fileInput} type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Button size="sm" disabled={!file || busy} leadingIcon={<Icon name="image" size={15} />}>
            {busy ? "Uploading..." : "Upload"}
          </Button>
        </form>
      )}

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={images.length === 0}
        emptyTitle="No report images yet"
        emptyText={canManage ? "Upload logos and site photos to match the reference report." : "No images have been uploaded."}
        onRetry={reload}
      >
        <div className={styles.assetGrid}>
          {images.map((image) => (
            <article className={styles.assetCard} key={image.id}>
              <Image
                className={styles.assetThumb}
                src={image.url}
                alt={image.caption || image.image_type_display}
                width={320}
                height={200}
                unoptimized
              />
              <div className={styles.assetMeta}>
                <span className={styles.assetType}>{image.image_type_display}</span>
                {image.caption && <span className={styles.assetCaption}>{image.caption}</span>}
              </div>
              {canManage && (
                <button className={styles.assetDelete} type="button" onClick={() => remove(image)} aria-label="Delete image">
                  <Icon name="trash" size={15} />
                </button>
              )}
            </article>
          ))}
        </div>
      </StateView>
    </section>
  );
}
