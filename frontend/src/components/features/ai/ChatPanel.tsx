"use client";

// Message list + streaming. `sessionId === null` means "not created yet" —
// the first sent message lazily creates the session so opening the page never
// litters the list with empty conversations.
import { useEffect, useRef, useState } from "react";

import { StateView } from "@/components/ui/StateView";
import { api, streamPost } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { AiProposal, AiStreamEvent, ChatMessageRow } from "@/types/ai";
import { MessageInput } from "./MessageInput";
import { ProposalCard } from "./ProposalCard";
import styles from "./ai.module.css";

interface Props {
  sessionId: string | null;
  createModel: string;
  onSessionCreated: (id: string) => void;
}

interface DisplayMessage extends ChatMessageRow {
  pendingProposal?: { messageId: string; proposal: AiProposal };
}

export function ChatPanel({ sessionId, createModel, onSessionCreated }: Props) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: history, loading, error } = useFetch(
    () => (sessionId ? api.get<ChatMessageRow[]>(`/ai/sessions/${sessionId}/messages/`) : Promise.resolve([])),
    [sessionId],
  );

  useEffect(() => {
    setMessages(history ?? []);
  }, [history]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function send(content: string, file: File | null) {
    setSendError(null);
    let id = sessionId;
    if (!id) {
      const session = await api.post<{ id: string }>("/ai/sessions/", createModel ? { model: createModel } : {});
      id = session.id;
      // Deliberately NOT calling onSessionCreated yet — it changes the parent's
      // `active` state, which this panel is keyed on (see AiChatPage), and
      // remounting mid-stream would blow away the in-flight message/error
      // state below. Told the parent once streaming finishes instead.
    }

    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: "user", content, tool_name: "", created_at: new Date().toISOString(),
        attachments: file ? [{ id: "local", original_filename: file.name, content_type: file.type, size_bytes: file.size }] : [] },
      { id: "streaming", role: "assistant", content: "", tool_name: "", created_at: new Date().toISOString(), attachments: [] },
    ]);
    setStreaming(true);

    const form = new FormData();
    form.append("content", content);
    if (file) form.append("file", file);

    try {
      for await (const event of streamPost<AiStreamEvent>(`/ai/sessions/${id}/messages/send/`, form)) {
        if (event.type === "delta") {
          // Pure updater — React 18 Strict Mode (on by default in `next dev`)
          // invokes state updaters twice to catch impure ones. The previous
          // version mutated `last.content` in place, so the double-invoke
          // appended every delta twice, doubling every word in the reply.
          setMessages((prev) => {
            const idx = prev.length - 1;
            if (prev[idx]?.id !== "streaming") return prev;
            const next = [...prev];
            next[idx] = { ...next[idx], content: next[idx].content + event.content };
            return next;
          });
        } else if (event.type === "proposal") {
          setMessages((prev) => {
            const idx = prev.length - 1;
            if (prev[idx]?.id !== "streaming") return prev;
            const next = [...prev];
            next[idx] = { ...next[idx], pendingProposal: { messageId: event.message_id, proposal: event.proposal } };
            return next;
          });
        } else if (event.type === "error") {
          setSendError(event.message);
        }
      }
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Couldn't reach the assistant.");
    } finally {
      setStreaming(false);
      // Drop the placeholder if nothing ever streamed into it (e.g. an error
      // before the first delta) — otherwise finalize it with a real id.
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== "streaming" || m.content)
          .map((m) => (m.id === "streaming" ? { ...m, id: `done-${Date.now()}` } : m)),
      );
      if (!sessionId && id) onSessionCreated(id);
    }
  }

  const placeholder = messages.find((m) => m.id === "streaming");
  const isThinking = streaming && !placeholder?.content.trim() && !placeholder?.pendingProposal;

  return (
    <div className={styles.panel}>
      <StateView loading={loading} error={error} isEmpty={false}>
        <div className={styles.messages}>
          {messages.length === 0 && !streaming && (
            <div className={styles.emptyState}>
              Ask about any project, request insights, or attach a schedule file to import.
            </div>
          )}
          {messages
            // A tool-call-only assistant turn (e.g. "call list_projects") has
            // no text of its own — real data, not a bug, but nothing to show
            // as a bubble unless it's also carrying a proposal card.
            .filter((m) => (m.role === "user" || m.role === "assistant") && (m.content.trim() || m.pendingProposal))
            .map((m) => (
              <div key={m.id} className={`${styles.bubble} ${m.role === "user" ? styles.bubbleUser : styles.bubbleAssistant}`}>
                <div className={styles.bubbleContent}>{m.content}</div>
                {m.attachments.map((a) => (
                  <div key={a.id} className={styles.attachmentChip}>{a.original_filename}</div>
                ))}
                {m.pendingProposal && (
                  <ProposalCard
                    sessionId={sessionId!}
                    messageId={m.pendingProposal.messageId}
                    proposal={m.pendingProposal.proposal}
                    onResolved={() =>
                      setMessages((prev) =>
                        prev.map((row) => (row.id === m.id ? { ...row, pendingProposal: undefined } : row)),
                      )
                    }
                  />
                )}
              </div>
            ))}
          {isThinking && (
            <div className={`${styles.bubble} ${styles.bubbleAssistant} ${styles.thinking}`}>
              <span className={styles.dot} />
              <span className={styles.dot} />
              <span className={styles.dot} />
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </StateView>

      {sendError && <p className={styles.sendError}>{sendError}</p>}
      <MessageInput disabled={streaming} onSend={send} />
    </div>
  );
}
