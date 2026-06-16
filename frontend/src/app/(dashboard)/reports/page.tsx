// Reports Hub route. View needs project access; EXPORT_REPORTS unlocks create/edit.
import { redirect } from "next/navigation";

import { ReportsHub } from "@/components/features/reports/ReportsHub";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ReportsPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const canView =
    user.is_platform_admin ||
    user.permissions.includes(Permission.VIEW_PROJECTS) ||
    user.permissions.includes(Permission.EXPORT_REPORTS);
  if (!canView) redirect(ROUTES.dashboard);

  const canManage = user.is_platform_admin || user.permissions.includes(Permission.EXPORT_REPORTS);
  return <ReportsHub canManage={canManage} />;
}
