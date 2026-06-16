"use client";

// Per-report content images: cover, progress photos (4/page), and attachments
// (1/page). Uploaded right in the Report Builder, rendered into the PDF.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ReportImage, ReportImageKind } from "@/types/report";
import styles from "./reports.module.css";

const KINDS: { value: ReportImageKind; label: string }[] = [
  { value: "cover", label: "Cover image" },
  { value: "progress", label: "Progress photo" },
  { value: "attachment", label: "Attachment" },
];

export function ReportAssets({
  reportId,
  canManage,
  onChanged,
}: {
  reportId: string;
  canManage: boolean;
  onChanged?: () => void;
}) {
  const [kind, setKind] = useState<ReportImageKind>("progress");
  const [caption, setCaption] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<ReportImage[]>(`/reports/${reportId}/images/`),
    [reportId],
  );
  const images = Array.isArray(data) ? data : [];

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setActionError(null);
    try {
      const form = new FormData();
      form.append("image", file);
      form.append("kind", kind);
      form.append("caption", caption);
      await api.uploadApi<ReportImage>(`/reports/${reportId}/images/`, form);
      setFile(null);
      setCaption("");
      reload();
      onChanged?.();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't upload image.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(image: ReportImage) {
    setActionError(null);
    try {
      await api.del(`/reports/${reportId}/images/${image.id}/`);
      reload();
      onChanged?.();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete image.");
    }
  }

  return (
    <section className={styles.assetCard}>
      <header className={styles.cardHead}>
        <h2 className={styles.cardTitle}>Report images</h2>
        <p className={styles.hint}>Cover (cover page), progress photos (4/page), and attachments (1/page).</p>
      </header>

      {canManage && (
        <form className={styles.assetForm} onSubmit={upload}>
          <select className={styles.assetSelect} value={kind} onChange={(e) => setKind(e.target.value as ReportImageKind)}>
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
          <input className={styles.assetInput} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Caption (optional)" />
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Button size="sm" disabled={!file || busy} leadingIcon={<Icon name="image" size={15} />}>
            {busy ? "Uploading…" : "Upload"}
          </Button>
        </form>
      )}

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={images.length === 0}
        emptyTitle="No images yet"
        emptyText={canManage ? "Upload a cover, progress photos, or attachments." : "No images uploaded."}
        onRetry={reload}
      >
        <div className={styles.assetGrid}>
          {images.map((image) => (
            <div className={styles.assetItem} key={image.id}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className={styles.assetThumb} src={image.url} alt={image.caption || image.kind_display} />
              <span className={styles.assetTag}>{image.kind_display}</span>
              {image.caption && <span className={styles.assetCaption}>{image.caption}</span>}
              {canManage && (
                <button className={styles.assetDelete} type="button" onClick={() => remove(image)} aria-label="Delete">
                  <Icon name="trash" size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      </StateView>
    </section>
  );
}
