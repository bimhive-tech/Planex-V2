// Report image upload front door (cover/progress/attachment/canvas). Same
// reasoning as /upload/import/[id]/route.ts: Next's /api rewrite proxy can
// drop a multipart body mid-stream during a dev-mode Fast Refresh recompile
// (surfaces to the browser as a broken, non-JSON response — "Upload failed."
// from api.uploadApi's fallback message), so this buffers the upload and
// forwards it to Django with a normal server-side fetch instead.
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

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/reports/${id}/images/`, {
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
