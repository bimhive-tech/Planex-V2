// Ask AI route. Gated by canUseAi (company.ai_enabled AND USE_AI_ASSISTANT) —
// deliberately no platform-admin bypass, since the platform company itself
// won't normally have this switched on.
import { redirect } from "next/navigation";

import { AiChatPage } from "@/components/features/ai/AiChatPage";
import { getCurrentUser } from "@/lib/server-auth";
import { canUseAi } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";

export default async function AiPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);
  if (!canUseAi(user)) redirect(ROUTES.dashboard);

  return <AiChatPage />;
}
