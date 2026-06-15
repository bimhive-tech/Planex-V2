// Root route: bounce to the dashboard (middleware redirects to login if no session).
import { redirect } from "next/navigation";
import { ROUTES } from "@/lib/constants";

export default function Home() {
  redirect(ROUTES.dashboard);
}
