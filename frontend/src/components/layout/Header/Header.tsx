"use client";

// Top header: mobile hamburger, global search, notification/help icons.
import { Icon } from "@/components/ui/Icon";
import { NotificationBell } from "./NotificationBell";
import { GlobalSearch } from "./GlobalSearch";
import styles from "./Header.module.css";

interface Props {
  onMenuClick: () => void;
  canSearch: boolean;
}

export function Header({ onMenuClick, canSearch }: Props) {
  return (
    <header className={styles.header}>
      <button className={styles.menuBtn} onClick={onMenuClick} aria-label="Open menu">
        <Icon name="menu" />
      </button>

      {canSearch ? <GlobalSearch /> : <div className={styles.spacer} />}

      <div className={styles.actions}>
        <NotificationBell />
        <button className={styles.iconBtn} aria-label="Help">
          <Icon name="help" />
        </button>
      </div>
    </header>
  );
}
