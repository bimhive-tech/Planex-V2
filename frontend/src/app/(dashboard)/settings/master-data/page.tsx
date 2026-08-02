import { redirect } from "next/navigation";

import { MasterDataTab } from "@/components/features/settings/MasterDataTab";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function MasterDataPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  const allowed = user.is_platform_admin || user.permissions.includes(Permission.MANAGE_MASTER_DATA);
  if (!allowed) redirect("/settings/info");
  return <MasterDataTab isPlatformAdmin={user.is_platform_admin} ownCompanyId={user.company?.id ?? ""} />;
}
