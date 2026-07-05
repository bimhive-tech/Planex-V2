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
  // Tab/module visibility comes from the user's PER-PROJECT permissions (admins
  // get all of them from the backend); company MANAGE_PROJECTS still gates admin
  // actions such as editing the project.
  const P = new Set(project.my_project_permissions);
  const perms = {
    manage: has(Permission.MANAGE_PROJECTS),
    overview: P.has("overview"),
    schedule: P.has("schedule"),
    team: P.has("team"),
    areasOfConcern: P.has("areas_of_concern"),
    submittals: P.has("submittals"),
    reports: P.has("reports"),
    submit: P.has("submit_progress"),
    review: P.has("review"),
    approve: P.has("approve"),
    deletePhotos: has(Permission.MANAGE_PROJECTS) || has(Permission.DELETE_PROGRESS_IMAGES),
    viewFinances: P.has("finances_view"),
    manageFinances: P.has("finances_manage"),
    exportReports: P.has("reports"),
  };
  return <ProjectWorkspace project={project} canManage={perms.manage} perms={perms} />;
}
