// Dashboard landing. Placeholder content for now — confirms the authenticated
// session resolved server-side. Real role-relevant widgets land in a later module.
import { getCurrentUser } from "@/lib/server-auth";
import styles from "./dashboard.module.css";

export default async function DashboardPage() {
  // Layout already guarantees a user; re-read here for page content.
  const user = await getCurrentUser();
  if (!user) return null;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Welcome back, {user.first_name || user.full_name}</h1>
        <p className={styles.subtitle}>
          {user.company?.name ?? "—"}
          {user.is_platform_admin && <span className={styles.tag}>Platform</span>}
        </p>
      </header>

      <section className={styles.grid}>
        <article className={styles.card}>
          <span className={styles.cardLabel}>Company</span>
          <span className={styles.cardValue}>{user.company?.name ?? "—"}</span>
        </article>
        <article className={styles.card}>
          <span className={styles.cardLabel}>Role</span>
          <span className={styles.cardValue}>
            {user.roles[0] ?? (user.is_platform_admin ? "Platform Admin" : "Member")}
          </span>
        </article>
        <article className={styles.card}>
          <span className={styles.cardLabel}>Email</span>
          <span className={styles.cardValue}>{user.email}</span>
        </article>
        <article className={styles.card}>
          <span className={styles.cardLabel}>Permissions</span>
          <span className={`${styles.cardValue} tnum`}>{user.permissions.length}</span>
        </article>
      </section>

      <section className={styles.panel}>
        <h2 className={styles.panelTitle}>Getting started</h2>
        <p className={styles.panelText}>
          Authentication is live. Next modules — companies, users, and projects — will appear in the
          sidebar as they’re built.
        </p>
      </section>
    </div>
  );
}
