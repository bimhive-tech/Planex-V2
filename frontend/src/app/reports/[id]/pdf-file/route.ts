// Report PDF front door. Large reports take a long time to render, and Next's
// rewrite proxy resets long upstream responses (~60s) — the same limitation the
// import upload works around. This route handler fetches the PDF from Django
// server-side (cookies forwarded) and streams it back, so the long render isn't
// cut off. Section-page map header is forwarded for the builder's tab scrolling.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/pdf/`, {
    headers: { cookie },
  });

  if (!res.ok) {
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
  }

  const headers = new Headers();
  headers.set("content-type", res.headers.get("content-type") ?? "application/pdf");
  const disposition = res.headers.get("content-disposition");
  if (disposition) headers.set("content-disposition", disposition);
  const sectionPages = res.headers.get("x-section-pages");
  if (sectionPages) headers.set("x-section-pages", sectionPages);

  return new Response(res.body, { status: 200, headers });
}
