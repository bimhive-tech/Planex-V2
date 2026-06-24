"use client";

// Cross-project approvals inbox: every submission awaiting THIS user's review
// or final approval, across all their company's projects. Decisions reuse the
// per-project review/approve endpoints (rows carry project_id).
import { useState } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { RejectModal } from "./RejectModal";
import { AuditTrailDrawer } from "./AuditTrailDrawer";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import type { InboxResponse, InboxSubmission } from "@/types/approvals";
import styles from "./approvalsInbox.module.css";

type Stage = "review" | "approve";

export function ApprovalsInbox({ canReview, canApprove }: { canReview: boolean; canApprove: boolean }) {
  // Default tab: reviewers land on "review", approve-only users on "approve".
  const [tab, setTab] = useState<Stage>(canReview ? "review" : "approve");
  const showTabs = canReview && canApprove;
  const stage = showTabs ? tab : canReview ? "review" : "approve";

  const { data, loading, error, reload } = useFetch(
    () => api.get<InboxResponse>(`/approvals/?stage=${stage}`),
    [stage],
  );
  const [reject, setReject] = useState<InboxSubmission | null>(null);
  const [trail, setTrail] = useState<InboxSubmission | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const rows = data?.results ?? [];

  async function decide(sub: InboxSubmission, decision: "approve" | "reject", comment = "") {
    setActionError(null);
    const s: Stage = sub.status === "pending_review" ? "review" : "approve";
    try {
      await api.post(`/projects/${sub.project_id}/submissions/${sub.id}/${s}/`, { decision, comment });
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't process this.");
      throw err;
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Approvals</h1>
        <p className={styles.subtitle}>Submissions waiting on your decision, across all projects.</p>
      </header>

      {showTabs && (
        <div className={styles.tabs}>
          <button className={`${styles.tab} ${stage === "review" ? styles.active : ""}`} onClick={() => setTab("review")}>
            To review{data ? <span className={styles.count}>{data.review_count}</span> : null}
          </button>
          <button className={`${styles.tab} ${stage === "approve" ? styles.active : ""}`} onClick={() => setTab("approve")}>
            To approve{data ? <span className={styles.count}>{data.approve_count}</span> : null}
          </button>
        </div>
      )}

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={rows.length === 0}
        emptyTitle="All caught up"
        emptyText="Nothing is waiting on your decision right now."
        onRetry={reload}
      >
        <div className={styles.list}>
          {rows.map((s) => (
            <div key={s.id} className={styles.card}>
              <div className={styles.cardMain}>
                <div className={styles.cardTop}>
                  <Link href={`/projects/${s.project_id}`} className={styles.project}>
                    <Icon name="projects" size={13} />{s.project_name}
                  </Link>
                  <Badge tone={s.status === "pending_review" ? "warning" : "info"}>{s.status_display}</Badge>
                </div>
                <span className={styles.activity}>{s.activity_name}</span>
                <span className={styles.path}>{s.activity_path}</span>
                <div className={styles.values}>
                  <span className="tnum">{Number(s.previous_progress)}%</span>
                  <span className={styles.arrow}>→</span>
                  <span className={`${styles.newVal} tnum`}>{Number(s.submitted_progress)}%</span>
                </div>
                <span className={styles.meta}>by {s.submitted_by_name || "—"} · {formatDate(s.created_at)}</span>
                {s.note && <p className={styles.note}>“{s.note}”</p>}
              </div>
              <div className={styles.cardActions}>
                <Button size="sm" onClick={() => decide(s, "approve")}>Approve</Button>
                <Button size="sm" variant="secondary" onClick={() => setReject(s)}>Reject</Button>
                <Button size="sm" variant="ghost" onClick={() => setTrail(s)}>History</Button>
              </div>
            </div>
          ))}
        </div>
      </StateView>

      {reject && (
        <RejectModal
          onClose={() => setReject(null)}
          onReject={async (comment) => { await decide(reject, "reject", comment); setReject(null); }}
        />
      )}

      <AuditTrailDrawer submission={trail} onClose={() => setTrail(null)} />
    </div>
  );
}
