// Account Settings — the signed-in user's own profile, roles, effective
// permissions, and a self-service password change. Server-rendered; the
// password form is the only client island.
import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { ChangePasswordForm } from "@/components/features/account/ChangePasswordForm";
import { getCurrentUser } from "@/lib/server-auth";
import { ROUTES } from "@/lib/constants";
import styles from "@/components/features/account/account.module.css";

// "view_projects" -> "View projects"
function humanize(key: string): string {
  const s = key.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      <span className={styles.rowValue}>{children}</span>
    </div>
  );
}

export default async function AccountPage() {
  const user = await getCurrentUser();
  if (!user) redirect(ROUTES.login);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Account settings</h1>
        <p className={styles.subtitle}>Your profile, access, and password.</p>
      </header>

      <div className={styles.grid}>
        {/* Profile */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>Profile</h2>
          <Row label="Name">{user.full_name || "—"}</Row>
          <Row label="Email">{user.email}</Row>
          <Row label="Phone">{user.phone_number || "—"}</Row>
          <Row label="Company">
            {user.company?.name ?? "—"}
            {user.is_platform_admin && <span className={styles.tag}>Platform</span>}
          </Row>
        </section>

        {/* Access */}
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>Access</h2>
          <div className={styles.accessBlock}>
            <span className={styles.accessLabel}>Roles</span>
            <div className={styles.chips}>
              {user.roles.length > 0 ? (
                user.roles.map((r) => <Badge key={r} tone="info">{r}</Badge>)
              ) : (
                <span className={styles.muted}>{user.is_platform_admin ? "Platform Admin" : "No roles"}</span>
              )}
            </div>
          </div>
          <div className={styles.accessBlock}>
            <span className={styles.accessLabel}>Permissions ({user.permissions.length})</span>
            {user.is_platform_admin ? (
              <span className={styles.muted}>Full platform access — all permissions.</span>
            ) : user.permissions.length > 0 ? (
              <div className={styles.chips}>
                {user.permissions.map((p) => <span key={p} className={styles.permChip}>{humanize(p)}</span>)}
              </div>
            ) : (
              <span className={styles.muted}>No permissions assigned.</span>
            )}
          </div>
        </section>

        {/* Password */}
        <section className={`${styles.card} ${styles.full}`}>
          <h2 className={styles.cardTitle}>Change password</h2>
          <p className={styles.cardSub}>Use at least 8 characters. You&apos;ll stay signed in after changing it.</p>
          <ChangePasswordForm />
        </section>
      </div>
    </div>
  );
}
