"use client";

// Fetches a PDF as raw bytes so react-pdf's <Document> can be given
// file={{data}} instead of a URL string. pdf.js's own network-stream code
// (used when <Document file> is a URL, including blob: URLs) hangs forever
// mid-render in this environment — the page "loads" (onLoadSuccess fires)
// but rendering never resolves or rejects (no onRenderSuccess/onRenderError
// either), with an uncaught "Failed to construct 'Headers': Invalid name"
// from pdf.js's PDFNetworkStreamFullRequest escaping to the console. Handing
// it already-fetched bytes skips that code path entirely.
import { useEffect, useState } from "react";

export function usePdfBytes(url: string | null): Uint8Array | null {
  const [bytes, setBytes] = useState<Uint8Array | null>(null);

  useEffect(() => {
    if (!url) {
      setBytes(null);
      return;
    }
    let alive = true;
    setBytes(null);
    fetch(url, { credentials: "include" })
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error("fetch failed"))))
      .then((buf) => { if (alive) setBytes(new Uint8Array(buf)); })
      .catch(() => { if (alive) setBytes(null); });
    return () => { alive = false; };
  }, [url]);

  return bytes;
}
