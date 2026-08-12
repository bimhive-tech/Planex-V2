// Report page-background images front door. Rasterizing every page (full PDF
// render + PyMuPDF) can take well over a minute on a large report, and Next's
// rewrite proxy resets long upstream responses (~60s) — the same limitation
// the PDF download and live-data routes work around (see ../pdf-file and
// ../data-file). Fetches the JSON from Django server-side (cookies
// forwarded) so a slow render isn't cut off mid-flight.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";
  const engine = req.nextUrl.searchParams.get("engine");
  const qs = engine ? `?engine=${encodeURIComponent(engine)}` : "";

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/page-images/${qs}`, {
    headers: { cookie },
  });

  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
