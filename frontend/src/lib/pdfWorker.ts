// Configures react-pdf's (pdf.js) worker exactly once, self-hosted (bundled
// by webpack — no external CDN). Import this module (for its side effect)
// anywhere `Document`/`Page` from "react-pdf" is used — PdfViewer and the
// Report Customize tab's real-page background both need it, and either one
// might load before the other depending on which tab the user opens first.
import { pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/** Pass as <Document options={PDF_DOCUMENT_OPTIONS}>. pdf.js's range/stream
 * fetcher throws ("Failed to construct 'Headers': Invalid name") against
 * both blob: URLs (PdfViewer's live preview) and this app's own PDF route,
 * silently leaving every page canvas blank with no visible error — a known
 * pdf.js incompatibility with how the response headers come back here.
 * Disabling range/stream requests makes it fetch the whole file up front
 * instead, which sidesteps the buggy code path entirely. A module-level
 * constant so the object reference is stable — a fresh object literal per
 * render would make react-pdf treat every render as a new document. */
export const PDF_DOCUMENT_OPTIONS = { disableStream: true, disableRange: true };
