// Customize tab's live table-continuation front door. Same reasoning as
// chart-svgs-file/toc-entries-file: cheap (no PDF assembly), but a
// dedicated handler rather than the /api proxy so a report with many
// overflowing tables can't hit the proxy's ~60s window.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";
  const body = await req.text();

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/table-overflow/`, {
    method: "POST",
    headers: { cookie, "content-type": "application/json" },
    body,
  });

  const responseBody = await res.text();
  return new Response(responseBody, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
