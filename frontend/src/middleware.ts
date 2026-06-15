// Edge route gate: cheap cookie-presence check. Real validation happens in the
// dashboard layout (server-side /me). Keeps unauthenticated users off app pages
// and signed-in users off the login page.
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { AUTH_COOKIE, ROUTES } from "@/lib/constants";

const PUBLIC_PATHS = [ROUTES.login];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  // trailingSlash:true means paths arrive as "/login/"; normalize for matching.
  const normalized = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  const hasSession =
    request.cookies.has(AUTH_COOKIE.access) || request.cookies.has(AUTH_COOKIE.refresh);
  const isPublic = PUBLIC_PATHS.includes(normalized as (typeof PUBLIC_PATHS)[number]);

  if (!hasSession && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = ROUTES.login;
    url.searchParams.set("next", normalized);
    return NextResponse.redirect(url);
  }

  if (hasSession && isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = ROUTES.dashboard;
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

// Run on everything except Next internals, the proxied API/admin, and static assets.
export const config = {
  matcher: ["/((?!api|admin|django-static|_next/static|_next/image|favicon.ico|healthz).*)"],
};
