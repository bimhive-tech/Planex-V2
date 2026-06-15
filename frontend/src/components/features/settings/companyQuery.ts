// Builds the ?company= query string used to scope settings requests. Empty when
// no company is selected (backend defaults to the caller's own company).
export function companyQuery(companyId: string | null, extra?: Record<string, string>): string {
  const params = new URLSearchParams();
  if (companyId) params.set("company", companyId);
  for (const [k, v] of Object.entries(extra ?? {})) {
    if (v) params.set(k, v);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}
