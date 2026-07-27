"use client";

// Ask AI page shell: session list (permanent rail on tablet+/off-canvas drawer
// on mobile, matching the app sidebar's own responsive pattern) + the active
// chat. Sessions are per-user, so no permission plumbing needed beyond the
// route gate already checked server-side.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { AiModelOption, ChatSessionRow } from "@/types/ai";
import { ChatPanel } from "./ChatPanel";
import styles from "./ai.module.css";

export function AiChatPage() {
  // `undefined` = no explicit choice yet -> default to the most recent
  // session. `null` = the user explicitly clicked "New chat" -> a blank
  // panel, even though a most-recent session exists. Collapsing these two
  // into one `null` value was a real bug: it made "New chat" silently
  // reselect the existing top session instead of starting fresh.
  const [activeId, setActiveId] = useState<string | null | undefined>(undefined);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The model for a session that doesn't exist yet — applied when the first
  // message lazily creates it. Once a session exists, its own `model` field
  // (edited via the selector below, PATCHed immediately) is what's shown.
  const [pendingModel, setPendingModel] = useState("");
  const { data: sessions, loading, error, reload } = useFetch(
    () => api.get<Paginated<ChatSessionRow>>("/ai/sessions/"),
    [],
  );
  const { data: models } = useFetch(() => api.get<AiModelOption[]>("/ai/models/"), []);

  const rows = sessions?.results ?? [];
  const active = activeId === undefined ? (rows[0]?.id ?? null) : activeId;
  const activeSession = rows.find((s) => s.id === active);
  const currentModel = activeSession ? activeSession.model : pendingModel;

  function select(id: string | null) {
    setActiveId(id);
    setDrawerOpen(false);
  }

  async function changeModel(modelId: string) {
    if (activeSession) {
      await api.patch(`/ai/sessions/${activeSession.id}/`, { model: modelId });
      reload();
    } else {
      setPendingModel(modelId);
    }
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
        <div className={styles.modelBar}>
          <Select
            aria-label="Model"
            className={styles.modelSelect}
            value={currentModel}
            options={[
              { value: "", label: "Default (Terra)" },
              ...(models ?? []).map((m) => ({
                value: m.id,
                label: `${m.label} — $${m.input_price}/$${m.output_price} per 1M tokens`,
              })),
            ]}
            onChange={(e) => changeModel(e.target.value)}
          />
        </div>
        <ChatPanel
          key={active ?? "new"}
          sessionId={active}
          createModel={pendingModel}
          onSessionCreated={(id) => {
            setActiveId(id);
            reload();
          }}
        />
      </div>
    </div>
  );
}
