"use client";

// Extra RichTextEditor toolbar buttons for a description element's on-canvas
// editing surface: insert a real table/chart/image inline in the flowing
// text — see backend/apps/reports/richtext.py's `_resolve_embed`, which
// turns the `<div data-embed="...">` marker this writes into the exact same
// Table/Drawing/Image the report's own standalone table/chart elements
// render with.
import { useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import { CHART_SOURCES, CHART_TYPES, TABLE_SOURCES } from "@/lib/reportElements";
import { embedHtml } from "@/lib/reportEmbeds";
import type { ReportImage } from "@/types/report";
import styles from "./DescriptionEmbedToolbar.module.css";

interface Props {
  /** Lets the image button upload to this report. Undefined in the project-
   * agnostic Template Builder — table/chart embeds still work there (they
   * just carry a source, resolved once a real report uses the template),
   * but there's no report yet to attach an uploaded image to, so that one
   * button is hidden. */
  reportId?: string;
  onInsert: (html: string) => void;
}

type EmbedKind = "table" | "chart";

export function DescriptionEmbedToolbar({ reportId, onInsert }: Props) {
  const [open, setOpen] = useState<EmbedKind | null>(null);
  const [source, setSource] = useState("");
  const [chartType, setChartType] = useState("bar");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function toggle(kind: EmbedKind) {
    setOpen((cur) => (cur === kind ? null : kind));
    setSource("");
  }

  function confirmInsert() {
    if (!source || !open) return;
    const sources = open === "table" ? TABLE_SOURCES : CHART_SOURCES;
    const label = sources.find((s) => s.value === source)?.label ?? source;
    const kindLabel = open === "table" ? "Table" : "Chart";
    onInsert(embedHtml(
      open,
      open === "table" ? { source } : { source, chart_type: chartType },
      `${kindLabel} — ${label}`,
    ));
    setOpen(null);
    setSource("");
  }

  async function handleImageFile(file: File) {
    if (!reportId) return;
    setUploading(true);
    setUploadError(null);
    try {
      // Routed through a Next.js route handler (images-file), not the /api
      // rewrite proxy directly — see that route's docstring: the proxy can
      // drop a multipart body mid-stream during a dev Fast Refresh recompile.
      const created = await api.upload<ReportImage>(`/reports/${reportId}/images-file`, file, "image", { kind: "canvas" });
      onInsert(embedHtml("image", { upload_id: created.id }, "Image"));
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Couldn't upload the image.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <button type="button" className={styles.btn} title="Insert table"
        onMouseDown={(e) => e.preventDefault()} onClick={() => toggle("table")}>
        <Icon name="table" size={16} />
      </button>
      <button type="button" className={styles.btn} title="Insert chart"
        onMouseDown={(e) => e.preventDefault()} onClick={() => toggle("chart")}>
        <Icon name="dashboard" size={16} />
      </button>
      {reportId && (
        <>
          <button type="button" className={styles.btn} title="Insert image" disabled={uploading}
            onMouseDown={(e) => e.preventDefault()} onClick={() => fileInputRef.current?.click()}>
            <Icon name="image" size={16} />
          </button>
          <input
            ref={fileInputRef} type="file" accept="image/*" hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleImageFile(file);
              e.target.value = ""; // same file re-selectable next time
            }}
          />
        </>
      )}

      {open && (
        <div className={styles.popover}>
          <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Data source">
            <option value="">Pick a data source…</option>
            {(open === "table" ? TABLE_SOURCES : CHART_SOURCES).map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          {open === "chart" && (
            <select value={chartType} onChange={(e) => setChartType(e.target.value)} aria-label="Chart type">
              {CHART_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          )}
          <button type="button" className={styles.confirm} disabled={!source} onClick={confirmInsert}>
            Insert
          </button>
        </div>
      )}
      {uploadError && <span className={styles.error}>{uploadError}</span>}
    </div>
  );
}
