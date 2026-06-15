// Settings shell: page header + permission-filtered subtab nav, then the subtab.
import { redirect } from "next/navigation";

import { SettingsTabs } from "@/components/features/settings/SettingsTabs";
import { getCurrentUser } from "@/lib/server-auth";
import { ROUTES } from "@/lib/constants";
import styles from "./settings.module.css";

export default async function SettingsLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Settings</h1>
        <p className={styles.subtitle}>Manage your company, users, roles, and access.</p>
      </header>
      <SettingsTabs user={user} />
      <div className={styles.content}>{children}</div>
    </div>
  );
}
