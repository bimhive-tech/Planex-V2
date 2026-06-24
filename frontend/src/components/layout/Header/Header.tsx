"use client";

// Top header: mobile hamburger, search field, notification/help icons.
import { Icon } from "@/components/ui/Icon";
import { NotificationBell } from "./NotificationBell";
import styles from "./Header.module.css";

interface Props {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: Props) {
  return (
    <header className={styles.header}>
      <button className={styles.menuBtn} onClick={onMenuClick} aria-label="Open menu">
        <Icon name="menu" />
      </button>

      <div className={styles.search}>
        <Icon name="search" size={18} />
        <input className={styles.searchInput} type="search" placeholder="Search…" aria-label="Search" />
      </div>

      <div className={styles.actions}>
        <NotificationBell />
        <button className={styles.iconBtn} aria-label="Help">
          <Icon name="help" />
        </button>
      </div>
    </header>
  );
}
