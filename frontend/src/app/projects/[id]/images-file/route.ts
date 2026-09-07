// Project image upload front door (logos / cover / site photos). Same
// reasoning as reports/[id]/images-file/route.ts: Next's /api rewrite proxy
// can drop a multipart body mid-stream, which surfaces as a broken non-JSON
// response ("Upload failed.") even though Django accepted the upload and
// created the row — seen live on a logo upload, 2026-09-07:
//   Failed to proxy .../api/projects/<id>/images/ [Error: socket hang up]
// Buffering here and forwarding with a normal server-side fetch avoids it.
import { NextRequest } from "next/server";

import { BACKEND_INTERNAL_URL } from "@/lib/constants";

export const runtime = "nodejs";
export const maxDuration = 120;

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const cookie = req.headers.get("cookie") ?? "";

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return Response.json({ error: { code: "bad_request", message: "Invalid upload." } }, { status: 400 });
  }

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/projects/${id}/images/`, {
    method: "POST",
    headers: { cookie },
    body: form,
  });

  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
