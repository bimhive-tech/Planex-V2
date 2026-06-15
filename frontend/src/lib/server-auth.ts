// Server-side auth helpers for Server Components. Calls Django directly
// (inside the same container) forwarding the request's auth cookies.
import "server-only";
import { cache } from "react";
import { cookies } from "next/headers";

import { BACKEND_INTERNAL_URL } from "./constants";
import type { CurrentUser } from "@/types/auth";

/**
 * Fetch the signed-in user, or null if unauthenticated.
 * Forwards incoming cookies so the JWT-cookie auth resolves server-side.
 * Wrapped in React cache() so multiple calls in one request (layout + page)
 * hit Django once.
 */
export const getCurrentUser = cache(async function getCurrentUser(): Promise<CurrentUser | null> {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader) return null;

  try {
    const res = await fetch(`${BACKEND_INTERNAL_URL}/api/auth/me/`, {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as CurrentUser;
  } catch {
    // Backend unreachable — treat as unauthenticated rather than crashing the page.
    return null;
  }
});
