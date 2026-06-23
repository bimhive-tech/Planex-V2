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
  const perms = {
    manage: has(Permission.MANAGE_PROJECTS),
    submit: has(Permission.SUBMIT_PROGRESS),
    review: has(Permission.REVIEW_PROGRESS),
    approve: has(Permission.APPROVE_PROGRESS),
    deletePhotos: has(Permission.MANAGE_PROJECTS) || has(Permission.DELETE_PROGRESS_IMAGES),
    viewFinances: has(Permission.VIEW_FINANCES) || has(Permission.MANAGE_FINANCES),
    manageFinances: has(Permission.MANAGE_FINANCES),
    exportReports: has(Permission.EXPORT_REPORTS),
  };
  return <ProjectWorkspace project={project} canManage={perms.manage} perms={perms} />;
}
