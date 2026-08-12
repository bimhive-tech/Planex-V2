// Customize tab's "Refresh preview" front door. Renders an UNSAVED draft
// layout (posted in the body) into real page-background images, the same
// heavy render + rasterize work as page-images — so it needs the same
// dedicated-route bypass of Next's /api rewrite proxy (~60s reset) as
// ../page-images-file and ../data-file.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";
  const body = await req.text();

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/preview-images/`, {
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
