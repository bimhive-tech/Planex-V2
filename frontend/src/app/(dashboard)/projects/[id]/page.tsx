// Project detail. Server-fetches the project (404 if not in the user's company),
// then renders the workspace shell (tabs).
import { notFound, redirect } from "next/navigation";

import { ProjectWorkspace } from "@/components/features/projects/ProjectWorkspace";
import { getCurrentUser } from "@/lib/server-auth";
import { getProject } from "@/lib/server-project";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const { id } = await params;
  const project = await getProject(id);
  if (!project) notFound();

  const has = (perm: string) => user.is_platform_admin || user.permissions.includes(perm);
  // Module access comes from the user's COMPANY role permissions — consistent
  // with everywhere else in the app. Scope (which data within a module) is
  // configured per-project-member instead (see the Team tab).
  const perms = {
    manage: has(Permission.MANAGE_PROJECTS),
    viewSchedule: has(Permission.VIEW_SCHEDULE),
    submit: has(Permission.SUBMIT_PROGRESS),
    review: has(Permission.REVIEW_PROGRESS),
    approve: has(Permission.APPROVE_PROGRESS),
    deletePhotos: has(Permission.MANAGE_PROJECTS) || has(Permission.DELETE_PROGRESS_IMAGES),
    viewAreasOfConcern: has(Permission.VIEW_AREAS_OF_CONCERN) || has(Permission.MANAGE_AREAS_OF_CONCERN),
    manageAreasOfConcern: has(Permission.MANAGE_AREAS_OF_CONCERN),
    viewSubmittals: has(Permission.VIEW_SUBMITTALS) || has(Permission.MANAGE_SUBMITTALS),
    manageSubmittals: has(Permission.MANAGE_SUBMITTALS),
    viewFinances: has(Permission.VIEW_FINANCES) || has(Permission.MANAGE_FINANCES),
    manageFinances: has(Permission.MANAGE_FINANCES),
    viewVariations: has(Permission.VIEW_VARIATIONS) || has(Permission.MANAGE_VARIATIONS),
    manageVariations: has(Permission.MANAGE_VARIATIONS),
    exportReports: has(Permission.EXPORT_REPORTS),
  };
  return <ProjectWorkspace project={project} canManage={perms.manage} perms={perms} />;
}
