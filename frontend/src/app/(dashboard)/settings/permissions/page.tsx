import { redirect } from "next/navigation";

import { PermissionsMatrix } from "@/components/features/settings/PermissionsMatrix";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function PermissionsPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  const allowed = user.is_platform_admin || user.permissions.includes(Permission.MANAGE_ROLES);
  if (!allowed) redirect("/settings/info");
  return <PermissionsMatrix isPlatformAdmin={user.is_platform_admin} ownCompanyId={user.company?.id ?? ""} />;
}
