import { redirect } from "next/navigation";

import { InfoTab } from "@/components/features/settings/InfoTab";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function InfoPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  const canEdit =
    user.is_platform_admin || user.permissions.includes(Permission.MANAGE_COMPANY);
  return <InfoTab canEdit={canEdit} />;
}
