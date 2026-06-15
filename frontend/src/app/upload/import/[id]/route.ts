// Large-file import endpoint. Next's rewrite proxy can't reliably stream big
// multipart bodies to upstream, so this route handler buffers the upload and
// forwards it to Django with a normal fetch (same-origin, cookies forwarded).
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

  const res = await fetch(`${BACKEND_INTERNAL_URL}/api/projects/${id}/import/`, {
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
