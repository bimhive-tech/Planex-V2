import { redirect } from "next/navigation";

import { UsersTab } from "@/components/features/settings/UsersTab";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function UsersPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  const allowed = user.is_platform_admin || user.permissions.includes(Permission.MANAGE_USERS);
  if (!allowed) redirect("/settings/info");
  return <UsersTab isPlatformAdmin={user.is_platform_admin} ownCompanyId={user.company?.id ?? ""} />;
}
