"use client";

// A pending write-action (create project / import a tree) the model proposed
// but did NOT execute — nothing is written until the user confirms here.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import type { AiProposal } from "@/types/ai";
import styles from "./ai.module.css";

interface Props {
  sessionId: string;
  messageId: string;
  proposal: AiProposal;
  onResolved: () => void;
}

export function ProposalCard({ sessionId, messageId, proposal, onResolved }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<"confirmed" | "cancelled" | null>(null);

  async function resolve(confirm: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/ai/sessions/${sessionId}/messages/${messageId}/confirm/`, { confirm });
      setResolution(confirm ? "confirmed" : "cancelled");
      onResolved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't complete this action.");
    } finally {
      setBusy(false);
    }
  }

  if (resolution) {
    return (
      <div className={styles.proposalCard}>
        <p>{resolution === "confirmed" ? "Done." : "Cancelled."}</p>
      </div>
    );
  }

  const counts = proposal.counts as { scopes: number; activities: number; milestones: number } | undefined;

  return (
    <div className={styles.proposalCard}>
      <p className={styles.proposalSummary}>{proposal.summary}</p>
      {counts && (
        <p className={styles.proposalCounts}>
          {counts.scopes} scopes · {counts.activities} activities · {counts.milestones} milestones
        </p>
      )}
      {error && <p className={styles.sendError}>{error}</p>}
      <div className={styles.proposalActions}>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => resolve(false)}>
          Cancel
        </Button>
        <Button size="sm" disabled={busy} onClick={() => resolve(true)}>
          {busy ? "Working…" : "Confirm"}
        </Button>
      </div>
    </div>
  );
}
