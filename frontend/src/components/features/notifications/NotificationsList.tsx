"use client";

// Full-page notifications list: All / Unread / Read tabs, mark-all-read, and
// per-item read. Clicking an item marks just that one read and navigates to
// the project it points to.
import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDateTime } from "@/lib/format";
import type { NotificationsResponse } from "@/types/notification";
import styles from "./notifications.module.css";

type Filter = "all" | "unread" | "read";
const TABS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "read", label: "Read" },
];

export function NotificationsList() {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("all");
  const { data, loading, error, reload } = useFetch(
    () => api.get<NotificationsResponse>(`/notifications/?filter=${filter}`),
    [filter],
  );
  const [busy, setBusy] = useState(false);
  const items = data?.results ?? [];
  const unread = data?.unread_count ?? 0;

  async function markRead(ids: string[]) {
    try {
      await api.post("/notifications/read/", { ids });
    } catch {
      /* best effort */
    }
  }

  async function markAllRead() {
    setBusy(true);
    try {
      await api.post("/notifications/read/");
      reload();
    } finally {
      setBusy(false);
    }
  }

  async function openItem(id: string, projectId: string | null, isRead: boolean) {
    if (!isRead) await markRead([id]);
    if (projectId) router.push(`/projects/${projectId}`);
    else reload();
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>Notifications</h1>
          <p className={styles.subtitle}>{unread > 0 ? `${unread} unread` : "You're all caught up."}</p>
        </div>
        {unread > 0 && (
          <Button variant="secondary" size="sm" disabled={busy} onClick={markAllRead}>Mark all read</Button>
        )}
      </header>

      <div className={styles.tabs}>
        {TABS.map((t) => (
          <button key={t.key} className={`${styles.tab} ${filter === t.key ? styles.active : ""}`}
            onClick={() => setFilter(t.key)}>
            {t.label}
            {t.key === "unread" && unread > 0 && <span className={styles.count}>{unread}</span>}
          </button>
        ))}
      </div>

      <StateView
        loading={loading} error={error} isEmpty={items.length === 0}
        emptyTitle={filter === "unread" ? "Nothing unread" : "No notifications"}
        emptyText="Updates about your submissions and approvals will show up here."
        onRetry={reload}
      >
        <ul className={styles.list}>
          {items.map((n) => (
            <li key={n.id}>
              <button
                className={`${styles.item} ${n.is_read ? "" : styles.unread}`}
                onClick={() => openItem(n.id, n.project_id, n.is_read)}
              >
                {!n.is_read && <span className={styles.dot} aria-hidden="true" />}
                <span className={styles.body}>
                  <span className={styles.message}>{n.message}</span>
                  <span className={styles.meta}>{n.kind_display} · {formatDateTime(n.created_at)}</span>
                </span>
                {n.project_id && <span className={styles.chevR}><Icon name="chevronDown" size={16} /></span>}
              </button>
            </li>
          ))}
        </ul>
      </StateView>
    </div>
  );
}
