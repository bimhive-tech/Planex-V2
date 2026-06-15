// Project Hub route. Requires view access; manage access unlocks create/edit.
import { redirect } from "next/navigation";

import { ProjectHub } from "@/components/features/projects/ProjectHub";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ProjectsPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const canView =
    user.is_platform_admin ||
    user.permissions.includes(Permission.VIEW_PROJECTS) ||
    user.permissions.includes(Permission.MANAGE_PROJECTS);
  if (!canView) redirect(ROUTES.dashboard);

  const canManage = user.is_platform_admin || user.permissions.includes(Permission.MANAGE_PROJECTS);
  return <ProjectHub canManage={canManage} />;
}
