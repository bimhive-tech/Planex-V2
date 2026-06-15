// Non-design constants: route paths, API base, page sizes. No magic literals.

// Browser-facing API base (same-origin; Next rewrites /api -> Django).
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

// Server-side direct address of Django (inside the same Railway container).
export const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

export const ROUTES = {
  login: "/login",
  dashboard: "/dashboard",
  home: "/",
} as const;

export const DEFAULT_PAGE_SIZE = 25;

// Auth cookie names — must match backend settings.AUTH_COOKIE_*.
export const AUTH_COOKIE = {
  access: "planex_access",
  refresh: "planex_refresh",
} as const;
