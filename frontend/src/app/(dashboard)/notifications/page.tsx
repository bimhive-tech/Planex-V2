// Notifications page — the full list of the user's notifications. Available to
// every signed-in user (notifications aren't permission-gated).
import { redirect } from "next/navigation";

import { NotificationsList } from "@/components/features/notifications/NotificationsList";
import { getCurrentUser } from "@/lib/server-auth";
import { ROUTES } from "@/lib/constants";

export default async function NotificationsPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  return <NotificationsList />;
}
