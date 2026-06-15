// Server-side fetch for a single project (used by the project detail page).
import "server-only";
import { cookies } from "next/headers";

import { BACKEND_INTERNAL_URL } from "./constants";
import type { ProjectDetail } from "@/types/project";

export async function getProject(id: string): Promise<ProjectDetail | null> {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader) return null;
  try {
    const res = await fetch(`${BACKEND_INTERNAL_URL}/api/projects/${id}/`, {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as ProjectDetail;
  } catch {
    return null;
  }
}
