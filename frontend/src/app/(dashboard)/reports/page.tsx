// Reports Hub route. EXPORT_REPORTS gates all report access (view + export).
import { redirect } from "next/navigation";

import { ReportsHub } from "@/components/features/reports/ReportsHub";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ReportsPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const canManage = user.is_platform_admin || user.permissions.includes(Permission.EXPORT_REPORTS);
  if (!canManage) redirect(ROUTES.dashboard);

  return <ReportsHub canManage={canManage} />;
}
