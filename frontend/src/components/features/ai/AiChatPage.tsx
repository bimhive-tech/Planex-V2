"use client";

// Ask AI page shell: session list (permanent rail on tablet+/off-canvas drawer
// on mobile, matching the app sidebar's own responsive pattern) + the active
// chat. Sessions are per-user, so no permission plumbing needed beyond the
// route gate already checked server-side.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ChatSessionRow } from "@/types/ai";
import { ChatPanel } from "./ChatPanel";
import styles from "./ai.module.css";

export function AiChatPage() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { data: sessions, loading, error, reload } = useFetch(
    () => api.get<Paginated<ChatSessionRow>>("/ai/sessions/"),
    [],
  );

  const rows = sessions?.results ?? [];
  const active = activeId ?? rows[0]?.id ?? null;

  function select(id: string | null) {
    setActiveId(id);
    setDrawerOpen(false);
  }

  const list = (
    <div className={styles.sessionList}>
      <Button
        size="sm"
        leadingIcon={<Icon name="plus" size={16} />}
        onClick={() => select(null)}
        className={styles.newChatBtn}
      >
        New chat
      </Button>
      <StateView loading={loading} error={error} isEmpty={rows.length === 0} emptyTitle="No conversations yet"
                 emptyText="Start a new chat to begin." onRetry={reload}>
        {rows.map((s) => (
          <button
            key={s.id}
            className={`${styles.sessionItem} ${s.id === active ? styles.sessionItemActive : ""}`}
            onClick={() => select(s.id)}
          >
            {s.title || "New chat"}
          </button>
        ))}
      </StateView>
    </div>
  );

  return (
    <div className={styles.page}>
      <aside className={styles.rail}>{list}</aside>

      <div className={styles.mobileHeader}>
        <button className={styles.mobileToggle} onClick={() => setDrawerOpen(true)} aria-label="Conversations">
          <Icon name="list" size={20} />
        </button>
        <span className={styles.mobileTitle}>Ask AI</span>
      </div>
      <Drawer open={drawerOpen} title="Conversations" onClose={() => setDrawerOpen(false)}>
        {list}
      </Drawer>

      <div className={styles.chatArea}>
        <ChatPanel
          key={active ?? "new"}
          sessionId={active}
          onSessionCreated={(id) => {
            setActiveId(id);
            reload();
          }}
        />
      </div>
    </div>
  );
}
