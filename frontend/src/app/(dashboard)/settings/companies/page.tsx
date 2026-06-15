import { redirect } from "next/navigation";

import { CompaniesTab } from "@/components/features/settings/CompaniesTab";
import { getCurrentUser } from "@/lib/server-auth";
import { ROUTES } from "@/lib/constants";

export default async function CompaniesPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  if (!user.is_platform_admin) redirect("/settings/info"); // platform-admin only
  return <CompaniesTab />;
}
