// Approvals inbox route. Visible to users who can review and/or approve
// progress; others are redirected away.
import { redirect } from "next/navigation";

import { ApprovalsInbox } from "@/components/features/approvals/ApprovalsInbox";
import { getCurrentUser } from "@/lib/server-auth";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function ApprovalsPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  const has = (p: string) => user.is_platform_admin || user.permissions.includes(p);
  const canReview = has(Permission.REVIEW_PROGRESS);
  const canApprove = has(Permission.APPROVE_PROGRESS);
  if (!canReview && !canApprove) redirect(ROUTES.dashboard);

  return <ApprovalsInbox canReview={canReview} canApprove={canApprove} />;
}
