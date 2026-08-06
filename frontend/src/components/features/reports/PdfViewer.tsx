"use client";

// Custom PDF preview (pdf.js via react-pdf): pages rendered as clean white
// sheets on a soft background, with a slim toolbar. Replaces the native iframe.
import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page } from "react-pdf";

import { Icon } from "@/components/ui/Icon";
import { usePdfBytes } from "@/hooks/usePdfBytes";
import { PDF_DOCUMENT_OPTIONS } from "@/lib/pdfWorker";
import styles from "./pdfViewer.module.css";

interface Props {
  url: string;
  loading: boolean;
  onDownload: () => void;
  scrollToPage?: number;  // 1-based page to scroll to (from the active tab)
  scrollNonce?: number;   // bump to re-trigger the scroll on the same target
}

export function PdfViewer({ url, loading, onDownload, scrollToPage, scrollNonce }: Props) {
  const [numPages, setNumPages] = useState(0);
  const [width, setWidth] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);

  // pdf.js's own network-stream fetch (used when <Document file> is a URL,
  // including this blob: one) hangs mid-render in this environment — see
  // usePdfBytes. Fetching the bytes ourselves and handing them over directly
  // skips that code path.
  const bytes = usePdfBytes(url || null);
  const file = useMemo(() => (bytes ? { data: bytes } : null), [bytes]);

  // Render pages at the container's width (responsive), capped for readability.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Scroll the requested page into view when the active tab changes.
  useEffect(() => {
    if (!scrollToPage || !numPages) return;
    const t = setTimeout(() => {
      pageRefs.current[scrollToPage - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
    return () => clearTimeout(t);
  }, [scrollToPage, scrollNonce, numPages]);

  const pageWidth = width > 0 ? Math.min(width - 32, 840) : undefined;

  return (
    <div ref={ref} className={styles.viewer}>
      <div className={styles.toolbar}>
        <span className={styles.count}>
          {url && numPages ? `${numPages} page${numPages === 1 ? "" : "s"}` : loading ? "Generating…" : "Preview"}
        </span>
        <button className={styles.dlBtn} type="button" onClick={onDownload}>
          <Icon name="download" size={14} /> Download
        </button>
      </div>

      <div className={styles.scroll}>
        {file ? (
          <Document
            file={file}
            options={PDF_DOCUMENT_OPTIONS}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            loading={<div className={styles.msg}>Loading preview…</div>}
            error={<div className={styles.msg}>Couldn&apos;t render the preview — use Download.</div>}
          >
            {Array.from({ length: numPages }, (_, i) => (
              <div className={styles.pageWrap} key={i} ref={(el) => { pageRefs.current[i] = el; }}>
                <Page
                  pageNumber={i + 1}
                  width={pageWidth}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                  loading=""
                  className={styles.page}
                />
              </div>
            ))}
          </Document>
        ) : (
          <div className={styles.msg}>{loading ? "Generating preview…" : "Preview unavailable — use Download."}</div>
        )}
      </div>
    </div>
  );
}
