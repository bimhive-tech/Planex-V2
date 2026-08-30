"use client";

// Upload a PDF, pick which of its pages to pull in as report images — each
// selected page is rendered to a PNG entirely in the browser (pdf.js, via
// react-pdf — already a dependency for the report PDF viewer) and uploaded
// through the exact same /reports/{id}/images/ endpoint a manually-picked
// image file already goes through, so nothing on the backend needs to know
// this image originated from a PDF page rather than a photo. Deliberately
// client-side: rasterizing an arbitrary uploaded PDF server-side would need
// a new backend dependency (PyMuPDF, AGPL-licensed unless a commercial
// license is purchased) for something the browser can already do for free.
import { useEffect, useState } from "react";
import { pdfjs } from "react-pdf";

import "@/lib/pdfWorker"; // configures pdfjs.GlobalWorkerOptions.workerSrc (side effect only)
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import type { ReportImage, ReportImageKind } from "@/types/report";
import styles from "./reports.module.css";

const THUMB_SCALE = 0.35;
// 144 DPI (scale 2 * pdf.js's 72-DPI-per-unit default) — matches the DPI
// this codebase's own retired PDF-page-rasterization endpoint used to render at.
const IMPORT_SCALE = 2;

interface PagePreview {
  index: number; // 1-based, matches pdf.js's own page numbering
  thumbUrl: string;
}

async function renderPageToBlob(pdf: pdfjs.PDFDocumentProxy, pageNumber: number, scale: number): Promise<Blob> {
  const page = await pdf.getPage(pageNumber);
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement("canvas");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas unavailable");
  await page.render({ canvasContext: ctx, viewport }).promise;
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Couldn't render page"))), "image/png");
  });
}

export function PdfPageImportPicker({
  reportId, kind, onImported,
}: {
  reportId: string;
  kind: ReportImageKind;
  onImported: () => void;
}) {
  const [pdf, setPdf] = useState<pdfjs.PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PagePreview[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loadingPages, setLoadingPages] = useState(false);
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Release pdf.js's own memory and the rendered thumbnails' object URLs
  // whenever this file is replaced or the picker unmounts.
  useEffect(() => () => { pdf?.destroy(); }, [pdf]);
  useEffect(() => () => { for (const p of pages) URL.revokeObjectURL(p.thumbUrl); }, [pages]);

  async function pickFile(file: File) {
    setError(null);
    setPages([]);
    setSelected(new Set());
    setPdf(null); // triggers the effect above, which destroys the previous doc
    setLoadingPages(true);
    try {
      const bytes = await file.arrayBuffer();
      const doc = await pdfjs.getDocument({ data: bytes }).promise;
      setPdf(doc);
      const previews: PagePreview[] = [];
      for (let i = 1; i <= doc.numPages; i++) {
        const blob = await renderPageToBlob(doc, i, THUMB_SCALE);
        previews.push({ index: i, thumbUrl: URL.createObjectURL(blob) });
      }
      setPages(previews);
      setSelected(new Set(previews.map((p) => p.index)));
    } catch {
      setError("Couldn't read this PDF — is it a valid, unencrypted PDF file?");
    } finally {
      setLoadingPages(false);
    }
  }

  function toggle(index: number) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(index)) next.delete(index); else next.add(index);
      return next;
    });
  }

  async function importSelected() {
    if (!pdf || selected.size === 0) return;
    setImporting(true);
    setError(null);
    const indices = [...selected].sort((a, b) => a - b);
    setProgress({ done: 0, total: indices.length });
    try {
      for (let i = 0; i < indices.length; i++) {
        const pageNumber = indices[i];
        const blob = await renderPageToBlob(pdf, pageNumber, IMPORT_SCALE);
        const form = new FormData();
        form.append("image", new File([blob], `page-${pageNumber}.png`, { type: "image/png" }));
        form.append("kind", kind);
        form.append("caption", `Page ${pageNumber}`);
        await api.uploadApi<ReportImage>(`/reports/${reportId}/images/`, form);
        setProgress({ done: i + 1, total: indices.length });
      }
      setPdf(null); // triggers the cleanup effect above, which destroys the doc
      setPages([]);
      setSelected(new Set());
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't import one of the pages.");
    } finally {
      setImporting(false);
      setProgress(null);
    }
  }

  return (
    <div className={styles.pdfImport}>
      <label className={styles.pdfImportPick}>
        <Icon name="reports" size={15} />
        <span>{pdf ? "Choose a different PDF…" : "Import pages from a PDF…"}</span>
        <input
          type="file" accept="application/pdf" hidden disabled={loadingPages || importing}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void pickFile(file);
            e.target.value = "";
          }}
        />
      </label>

      {loadingPages && <p className={styles.hint}>Reading pages…</p>}
      {error && <p className="formError">{error}</p>}

      {pages.length > 0 && (
        <>
          <div className={styles.pdfImportBar}>
            <span className={styles.hint}>{selected.size} of {pages.length} page{pages.length === 1 ? "" : "s"} selected</span>
            <button type="button" className={styles.pdfImportLink} onClick={() => setSelected(new Set(pages.map((p) => p.index)))}>
              Select all
            </button>
            <button type="button" className={styles.pdfImportLink} onClick={() => setSelected(new Set())}>
              Select none
            </button>
          </div>

          <div className={styles.pdfImportGrid}>
            {pages.map((p) => (
              <label key={p.index} className={styles.pdfImportPage} data-selected={selected.has(p.index) ? "on" : undefined}>
                <input type="checkbox" checked={selected.has(p.index)} onChange={() => toggle(p.index)} />
                {/* eslint-disable-next-line @next/next/no-img-element -- a local object URL, not an optimizable remote asset */}
                <img src={p.thumbUrl} alt={`Page ${p.index}`} />
                <span>{p.index}</span>
              </label>
            ))}
          </div>

          <Button size="sm" disabled={selected.size === 0 || importing} onClick={importSelected}>
            {progress ? `Importing ${progress.done}/${progress.total}…` : `Import ${selected.size} page${selected.size === 1 ? "" : "s"}`}
          </Button>
        </>
      )}
    </div>
  );
}
