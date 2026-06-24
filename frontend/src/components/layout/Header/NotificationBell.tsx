"use client";

// Header notification bell: unread badge + a dropdown of recent notifications,
// with mark-all-read and click-through to the related project. Polls lightly so
// the badge stays fresh without a websocket.
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Icon } from "@/components/ui/Icon";
import { useClickOutside } from "@/hooks/useClickOutside";
import { api } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import type { NotificationsResponse } from "@/types/notification";
import styles from "./NotificationBell.module.css";

const POLL_MS = 60_000;

export function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<NotificationsResponse | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);

  const load = useCallback(async () => {
    try {
      setData(await api.get<NotificationsResponse>("/notifications/"));
    } catch {
      // A failed poll shouldn't surface anything — the bell just won't update.
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const items = data?.results ?? [];
  const unread = data?.unread_count ?? 0;

  async function markAllRead() {
    setData((d) => (d ? { ...d, results: d.results.map((n) => ({ ...n, is_read: true })), unread_count: 0 } : d));
    try {
      await api.post("/notifications/read/");
    } catch {
      load(); // revert to server truth on failure
    }
  }

  function openItem(projectId: string | null) {
    setOpen(false);
    if (unread > 0) markAllRead();
    if (projectId) router.push(`/projects/${projectId}`);
  }

  return (
    <div className={styles.wrap} ref={ref}>
      <button className={styles.iconBtn} aria-label="Notifications" onClick={() => setOpen((o) => !o)}>
        <Icon name="bell" />
        {unread > 0 && <span className={styles.badge}>{unread > 9 ? "9+" : unread}</span>}
      </button>

      {open && (
        <div className={styles.panel} role="dialog" aria-label="Notifications">
          <div className={styles.panelHead}>
            <span className={styles.panelTitle}>Notifications</span>
            {unread > 0 && (
              <button className={styles.markRead} onClick={markAllRead}>Mark all read</button>
            )}
          </div>

          {items.length === 0 ? (
            <p className={styles.empty}>You&apos;re all caught up.</p>
          ) : (
            <ul className={styles.list}>
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    className={`${styles.item} ${n.is_read ? "" : styles.unread}`}
                    onClick={() => openItem(n.project_id)}
                  >
                    {!n.is_read && <span className={styles.dot} aria-hidden="true" />}
                    <span className={styles.message}>{n.message}</span>
                    <span className={styles.time}>{formatDate(n.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <Link href={ROUTES.notifications} className={styles.viewAll} onClick={() => setOpen(false)}>
            View all notifications
          </Link>
        </div>
      )}
    </div>
  );
}
