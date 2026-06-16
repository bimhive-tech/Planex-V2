// Templates Hub route. Designing templates requires EXPORT_REPORTS.
import { redirect } from "next/navigation";

import { TemplatesHub } from "@/components/features/reports/TemplatesHub";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ReportTemplatesPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const canManage = user.is_platform_admin || user.permissions.includes(Permission.EXPORT_REPORTS);
  if (!canManage) redirect(ROUTES.reports);

  return <TemplatesHub />;
}
