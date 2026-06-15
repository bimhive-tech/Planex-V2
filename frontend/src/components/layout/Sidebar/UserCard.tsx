"use client";

// Bottom-of-sidebar user card: initials avatar, name, role, logout.
import { Icon } from "@/components/ui/Icon";
import { api } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import type { CurrentUser } from "@/types/auth";
import styles from "./UserCard.module.css";

function initials(user: CurrentUser): string {
  const a = user.first_name?.[0] ?? user.email[0];
  const b = user.last_name?.[0] ?? "";
  return (a + b).toUpperCase();
}

export function UserCard({ user }: { user: CurrentUser }) {
  const roleLabel = user.roles[0] ?? (user.is_platform_admin ? "Platform Admin" : "Member");

  async function handleLogout() {
    try {
      await api.post("/auth/logout/");
    } finally {
      window.location.assign(ROUTES.login);
    }
  }

  return (
    <div className={styles.card}>
      <span className={styles.avatar} aria-hidden="true">
        {initials(user)}
      </span>
      <div className={styles.meta}>
        <span className={styles.name}>{user.full_name}</span>
        <span className={styles.role}>{roleLabel}</span>
      </div>
      <button className={styles.logout} onClick={handleLogout} aria-label="Sign out" title="Sign out">
        <Icon name="logout" size={18} />
      </button>
    </div>
  );
}
