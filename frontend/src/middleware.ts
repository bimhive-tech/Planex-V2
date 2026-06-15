// Route gate + silent token refresh.
//
// - Protected route with a valid access cookie → through.
// - Access cookie expired (gone) but refresh cookie present → call Django to mint
//   fresh tokens, set them on the response AND forward them to this same request so
//   the page renders signed-in (no redirect-to-login flicker, no loop on redeploy).
// - No/!invalid session → redirect to /login (clearing stale cookies).
//
// We deliberately do NOT bounce signed-in users away from /login by cookie presence
// alone — that was the cause of the infinite /login↔/dashboard loop when a cookie
// was present but no longer valid.
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { AUTH_COOKIE, BACKEND_INTERNAL_URL, ROUTES } from "@/lib/constants";

const PUBLIC_PATHS = [ROUTES.login];

function readSetCookieValue(setCookies: string[], name: string): string | null {
  for (const sc of setCookies) {
    const m = sc.match(new RegExp(`^${name}=([^;]+)`));
    if (m) return m[1];
  }
  return null;
}

function loginRedirect(request: NextRequest, next?: string) {
  const url = request.nextUrl.clone();
  url.pathname = ROUTES.login;
  url.search = "";
  if (next && next !== ROUTES.login) url.searchParams.set("next", next);
  const res = NextResponse.redirect(url);
  res.cookies.delete(AUTH_COOKIE.access);
  res.cookies.delete(AUTH_COOKIE.refresh);
  return res;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const normalized = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  const isPublic = PUBLIC_PATHS.includes(normalized as (typeof PUBLIC_PATHS)[number]);

  const access = request.cookies.get(AUTH_COOKIE.access)?.value;
  const refresh = request.cookies.get(AUTH_COOKIE.refresh)?.value;

  if (isPublic) return NextResponse.next();
  if (access) return NextResponse.next(); // assume valid; the page validates via /me
  if (!refresh) return loginRedirect(request, normalized);

  // Access expired but refresh present → try to mint a new access token.
  try {
    const r = await fetch(`${BACKEND_INTERNAL_URL}/api/auth/refresh/`, {
      method: "POST",
      headers: { cookie: `${AUTH_COOKIE.refresh}=${refresh}` },
    });
    if (!r.ok) return loginRedirect(request, normalized);

    const setCookies = r.headers.getSetCookie?.() ?? [];
    const newAccess = readSetCookieValue(setCookies, AUTH_COOKIE.access);
    const newRefresh = readSetCookieValue(setCookies, AUTH_COOKIE.refresh) ?? refresh;
    if (!newAccess) return loginRedirect(request, normalized);

    // Forward the fresh cookies to THIS request so the page renders authenticated.
    const others = request.cookies
      .getAll()
      .filter((c) => c.name !== AUTH_COOKIE.access && c.name !== AUTH_COOKIE.refresh)
      .map((c) => `${c.name}=${c.value}`);
    const cookieHeader = [
      ...others,
      `${AUTH_COOKIE.access}=${newAccess}`,
      `${AUTH_COOKIE.refresh}=${newRefresh}`,
    ].join("; ");

    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("cookie", cookieHeader);
    const res = NextResponse.next({ request: { headers: requestHeaders } });
    for (const c of setCookies) res.headers.append("set-cookie", c);
    return res;
  } catch {
    // Backend unreachable — send to login rather than loop.
    return loginRedirect(request, normalized);
  }
}

export const config = {
  matcher: ["/((?!api|admin|django-static|_next/static|_next/image|favicon.ico|healthz).*)"],
};
