// Server-side aggregate fetch for the dashboard landing. Forwards the request's
// auth cookies to Django (same container) and tolerates partial failures so one
// unreachable endpoint never blanks the whole page.
import "server-only";
import { cookies } from "next/headers";

import { BACKEND_INTERNAL_URL } from "./constants";
import type { ProjectListRow } from "@/types/project";

interface Page<T> {
  count: number;
  results: T[];
}

export interface DashboardData {
  projectCount: number;
  activeCount: number;
  reportCount: number | null; // null when the user can't view reports
  projects: ProjectListRow[];
}

async function fetchPage<T>(path: string, cookieHeader: string): Promise<Page<T> | null> {
  try {
    const res = await fetch(`${BACKEND_INTERNAL_URL}${path}`, {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as Page<T>;
  } catch {
    return null;
  }
}

export async function getDashboardData(): Promise<DashboardData> {
  const cookieHeader = (await cookies()).toString();
  const empty: DashboardData = { projectCount: 0, activeCount: 0, reportCount: null, projects: [] };
  if (!cookieHeader) return empty;

  // Run the independent reads in parallel — the page blocks on the slowest, not the sum.
  const [all, active, reports] = await Promise.all([
    fetchPage<ProjectListRow>("/api/projects/?status=all", cookieHeader),
    fetchPage<ProjectListRow>("/api/projects/?status=active", cookieHeader),
    fetchPage<unknown>("/api/reports/", cookieHeader),
  ]);

  return {
    projectCount: all?.count ?? 0,
    activeCount: active?.count ?? 0,
    reportCount: reports ? reports.count : null,
    projects: active?.results ?? all?.results ?? [],
  };
}
