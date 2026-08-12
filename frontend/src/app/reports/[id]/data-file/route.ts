// Report live-data front door. build_report_context() alone takes 30s+ on a
// large report, and Next's rewrite proxy resets long upstream responses
// (~60s) — the same limitation the PDF download works around (see
// ../pdf-file/route.ts). This fetches the data JSON from Django server-side
// (cookies forwarded) so a slow render isn't cut off mid-flight.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/data/`, {
    headers: { cookie },
  });

  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
