// Small formatting helpers.

const DATE_FMT = new Intl.DateTimeFormat("en", { year: "numeric", month: "short", day: "numeric" });

/** "Jun 15, 2026" from an ISO timestamp. */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}
