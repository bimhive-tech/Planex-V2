// Customize tab's live table preview front door — same reasoning as its
// chart-svgs-file sibling: cheap (plain JSON rows, not a rendered document)
// but still routed through a dedicated handler rather than the /api proxy,
// since a report with many tables could still add up.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";
  const body = await req.text();

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/table-data/`, {
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
