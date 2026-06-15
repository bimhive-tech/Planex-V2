// Authenticated shell layout. Server-side: resolve the user or redirect to login.
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell/AppShell";
import { getCurrentUser } from "@/lib/server-auth";
import { ROUTES } from "@/lib/constants";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  return <AppShell user={user}>{children}</AppShell>;
}
