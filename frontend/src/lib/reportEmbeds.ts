// The inline embed marker a description element's rich text can carry — a
// table/chart/image dropped or inserted into the flowing narrative, resolved
// server-side into a real Table/Drawing/Image by apps/reports/richtext.py's
// _resolve_embed (the exact same resolve_table/resolve_chart every
// standalone table/chart element already uses).
export type EmbedKind = "table" | "chart" | "image";

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** The marker itself — its own display children are never read back (see
 * richtext.py's _serialize, which drops an embed's children on save and
 * treats `data-spec` as the only source of truth), so the visible text here
 * is just a friendly label while editing. */
export function embedHtml(kind: EmbedKind, props: Record<string, unknown>, label: string): string {
  const spec = JSON.stringify({ kind, props }).replace(/'/g, "&#39;");
  const icon = kind === "table" ? "📊" : kind === "chart" ? "📈" : "🖼️";
  return `<div data-embed="${kind}" data-spec='${spec}' contenteditable="false">${icon} ${escapeHtml(label)}</div>`;
}
