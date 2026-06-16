// Template Builder route. Editing a template's design requires EXPORT_REPORTS.
import { redirect } from "next/navigation";

import { TemplateBuilder } from "@/components/features/reports/TemplateBuilder";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function TemplateBuilderPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const canManage = user.is_platform_admin || user.permissions.includes(Permission.EXPORT_REPORTS);
  if (!canManage) redirect(ROUTES.reports);

  const { id } = await params;
  return <TemplateBuilder templateId={id} />;
}
