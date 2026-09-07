"use client";

// Fill a logo/cover slot straight from the canvas properties panel, instead of
// leaving the Customize tab for Setup to do it (client ask, 2026-09-07).
//
// Unlike the "Uploaded image" source — which belongs to one box in one report —
// these slots are shared: the logos are the PROJECT's and appear on every
// report generated for it, and the cover is this report's. Each says which,
// because uploading here changes more than the box you're looking at.
import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ProjectImage, ProjectImageType } from "@/types/project";
import type { ReportImage } from "@/types/report";
import styles from "./designer.module.css";

/** The slots this control can fill, and where each is actually stored. Keep in
 * step with apps/reports/services.py's `logos` block, which is what resolves
 * them: left/right/extra read the project's images, while cover prefers this
 * report's own and only falls back to the project's. */
export const SLOT_TARGETS = {
  left: { scope: "project", type: "logo_left", note: "Shown on every report for this project." },
  right: { scope: "project", type: "logo_right", note: "Shown on every report for this project." },
  extra: { scope: "project", type: "logo", note: "Shown on every report for this project." },
  cover: { scope: "report", type: "cover", note: "Used on this report only." },
} as const;

export type SlotSource = keyof typeof SLOT_TARGETS;

export function isSlotSource(source: unknown): source is SlotSource {
  return typeof source === "string" && source in SLOT_TARGETS;
}

interface Props {
  source: SlotSource;
  /** Which of the additional logos, for the "extra" source only. */
  slot: number;
  reportId?: string;
  projectId?: string;
  /** Refetches the report's live data so the canvas redraws with the new image. */
  onUploaded?: () => void;
}

export function SlotImageUpload({ source, slot, reportId, projectId, onUploaded }: Props) {
  const target = SLOT_TARGETS[source];
  const isProject = target.scope === "project";
  const owner = isProject ? projectId : reportId;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetched here rather than read off liveData.logos: that copy is trimmed to
  // caption+url (see views.py's `light`), and replacing an image needs the id
  // of the one it replaces.
  const { data, reload } = useFetch(async () => {
    if (!owner) return [];
    if (isProject) {
      const all = await api.get<ProjectImage[] | Paginated<ProjectImage>>(`/projects/${owner}/images/`);
      const rows = Array.isArray(all) ? all : all.results;
      return rows.filter((i) => i.image_type === (target.type as ProjectImageType));
    }
    const all = await api.get<ReportImage[] | Paginated<ReportImage>>(`/reports/${owner}/images/`);
    const rows = Array.isArray(all) ? all : all.results;
    return rows.filter((i) => i.kind === "cover");
  }, [owner, isProject, target.type]);

  const rows = data ?? [];
  // "extra" addresses one of many by index; the rest are single slots, and the
  // renderer takes the first match for those.
  const current = source === "extra" ? rows[slot] : rows[0];

  async function handleUpload(file: File) {
    if (!owner) return;
    setBusy(true);
    setError(null);
    try {
      // Upload BEFORE removing what it replaces: a failed upload then leaves
      // the existing image untouched rather than destroying it.
      if (isProject) {
        const form = new FormData();
        form.append("image", file);
        form.append("image_type", target.type);
        form.append("caption", current?.caption ?? "");
        await api.uploadApi<ProjectImage>(`/projects/${owner}/images/`, form);
      } else {
        // Routed via the images-file route handler, not the /api proxy, which
        // can drop a multipart body mid-stream on a dev Fast Refresh.
        await api.upload<ReportImage>(`/reports/${owner}/images-file`, file, "image", { kind: "cover" });
      }
      // Nothing enforces one image per slot in the DB, and the renderer takes
      // the FIRST match — so without clearing the old one the upload looks
      // like it did nothing at all.
      if (current) {
        const path = isProject
          ? `/projects/${owner}/images/${current.id}/`
          : `/reports/${owner}/images/${current.id}/`;
        await api.del(path);
      }
      reload();
      onUploaded?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't upload the image.");
    } finally {
      setBusy(false);
    }
  }

  if (!owner) {
    return (
      <div className={styles.uploadBlock}>
        <p className={styles.panelHint}>
          Uploading is only available on a report&apos;s Customize tab, not the project-agnostic template.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.uploadBlock}>
      {current ? (
        // eslint-disable-next-line @next/next/no-img-element -- authed streaming URL, not an optimizable public asset
        <img className={styles.uploadPreview} src={current.url} alt="" />
      ) : (
        <p className={styles.panelHint}>Nothing in this slot yet.</p>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleUpload(file);
          e.target.value = ""; // same file re-selectable next time
        }}
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={busy}
        onClick={() => fileInputRef.current?.click()}
      >
        {busy ? "Uploading…" : current ? "Replace image" : "Upload image"}
      </Button>
      <p className={styles.panelHint}>{target.note}</p>
      {error && <p className="formError">{error}</p>}
    </div>
  );
}
