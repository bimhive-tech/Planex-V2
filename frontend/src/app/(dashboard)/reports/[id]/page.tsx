// Report detail route: preview/download the PDF and manage its report images.
import { redirect } from "next/navigation";

import { ReportDetail } from "@/components/features/reports/ReportDetail";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  // EXPORT_REPORTS gates all report access (view, edit, download).
  const canManage = user.is_platform_admin || user.permissions.includes(Permission.EXPORT_REPORTS);
  if (!canManage) redirect(ROUTES.dashboard);

  const { id } = await params;
  return <ReportDetail reportId={id} canManage={canManage} />;
}
