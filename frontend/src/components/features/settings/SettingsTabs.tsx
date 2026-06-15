"use client";

// Settings subtab nav. Tabs self-filter by the user's permissions / platform role.
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Permission } from "@/lib/permissions";
import type { CurrentUser } from "@/types/auth";
import styles from "./SettingsTabs.module.css";

interface Tab {
  label: string;
  href: string;
  show: (u: CurrentUser) => boolean;
}

const can = (u: CurrentUser, perm: string) => u.is_platform_admin || u.permissions.includes(perm);

const TABS: Tab[] = [
  { label: "Info", href: "/settings/info", show: () => true },
  { label: "Users", href: "/settings/users", show: (u) => can(u, Permission.MANAGE_USERS) },
  { label: "Companies", href: "/settings/companies", show: (u) => u.is_platform_admin },
  { label: "Roles", href: "/settings/roles", show: (u) => can(u, Permission.MANAGE_ROLES) },
];

export function SettingsTabs({ user }: { user: CurrentUser }) {
  const pathname = usePathname();
  const visible = TABS.filter((t) => t.show(user));

  return (
    <nav className={styles.tabs}>
      {visible.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`${styles.tab} ${active ? styles.active : ""}`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
