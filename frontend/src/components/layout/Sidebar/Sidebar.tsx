"use client";

// Sidebar: logo, permission-filtered nav, and the user card at the bottom.
import { usePathname } from "next/navigation";
import Link from "next/link";

import { Logo } from "@/components/ui/Logo";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { NAV_ITEMS } from "../nav";
import { UserCard } from "./UserCard";
import { hasPermission } from "@/lib/permissions";
import type { CurrentUser } from "@/types/auth";
import styles from "./Sidebar.module.css";

interface Props {
  user: CurrentUser;
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ user, open, onClose }: Props) {
  const pathname = usePathname();

  const items = NAV_ITEMS.filter((item) => {
    if (item.platformOnly && !user.is_platform_admin) return false;
    if (user.is_platform_admin) return true;
    if (item.permission && !hasPermission(user, item.permission)) return false;
    return true;
  });

  return (
    <aside className={`${styles.sidebar} ${open ? styles.open : ""}`}>
      <div className={styles.top}>
        <Logo showMark={false} />
      </div>

      <nav className={styles.nav}>
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const className = `${styles.item} ${active ? styles.active : ""} ${
            item.soon ? styles.soon : ""
          }`;
          const content = (
            <>
              <Icon name={item.icon as IconName} size={18} />
              <span>{item.label}</span>
              {item.soon && <span className={styles.badge}>Soon</span>}
            </>
          );
          return item.soon ? (
            <span key={item.href} className={className} aria-disabled="true">
              {content}
            </span>
          ) : (
            <Link key={item.href} href={item.href} className={className} onClick={onClose}>
              {content}
            </Link>
          );
        })}
      </nav>

      <div className={styles.bottom}>
        <UserCard user={user} />
      </div>
    </aside>
  );
}
