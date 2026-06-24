// Small formatting helpers.

const DATE_FMT = new Intl.DateTimeFormat("en", { year: "numeric", month: "short", day: "numeric" });
const DATETIME_FMT = new Intl.DateTimeFormat("en", {
  year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});

/** "Jun 15, 2026" from an ISO timestamp. */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

/** "Jun 15, 2026, 3:42 PM" from an ISO timestamp. */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATETIME_FMT.format(d);
}
