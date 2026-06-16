"use client";

// Approvals tab: the submission queue. Reviewers act on Pending Review,
// approvers (PM) on Pending PM Approval. A status filter shows history too.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import type { ProjectPerms, ProjectSubmission } from "@/types/project";
import styles from "./approvals.module.css";

const STATUS_TONE: Record<string, "info" | "warning" | "success" | "danger" | "neutral"> = {
  pending_review: "warning", pending_pm: "info", accepted: "success",
  reviewer_rejected: "danger", pm_rejected: "danger",
};
const FILTERS = [
  { value: "open", label: "Awaiting action" },
  { value: "", label: "All" },
  { value: "accepted", label: "Accepted" },
  { value: "reviewer_rejected", label: "Reviewer rejected" },
  { value: "pm_rejected", label: "PM rejected" },
];

export function ProjectApprovals({ projectId, perms, onChanged }: {
  projectId: string; perms: ProjectPerms; onChanged: () => void;
}) {
  const [filter, setFilter] = useState("open");
  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectSubmission[]>(`/projects/${projectId}/submissions/${filter ? `?status=${filter}` : ""}`),
    [projectId, filter],
  );
  const [reject, setReject] = useState<{ sub: ProjectSubmission; stage: "review" | "approve" } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const rows = data ?? [];

  async function decide(sub: ProjectSubmission, stage: "review" | "approve", decision: "approve" | "reject", comment = "") {
    setActionError(null);
    try {
      await api.post(`/projects/${projectId}/submissions/${sub.id}/${stage}/`, { decision, comment });
      reload();
      onChanged();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't process this.");
      throw err;
    }
  }

  function actionsFor(sub: ProjectSubmission) {
    if (sub.status === "pending_review" && perms.review) return "review" as const;
    if (sub.status === "pending_pm" && perms.approve) return "approve" as const;
    return null;
  }

  return (
    <div>
      <div className={styles.head}>
        <span className={styles.muted}>{rows.length} submissions</span>
        <Select className={styles.filter} options={FILTERS} value={filter}
          onChange={(e) => setFilter(e.target.value)} aria-label="Filter submissions" />
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={rows.length === 0}
        emptyTitle="Nothing here"
        emptyText={filter === "open" ? "No submissions are awaiting action." : "No submissions match this filter."}
        onRetry={reload}
      >
        <div className={styles.list}>
          {rows.map((s) => {
            const stage = actionsFor(s);
            return (
              <div key={s.id} className={styles.card}>
                <div className={styles.cardMain}>
                  <div className={styles.cardTop}>
                    <span className={styles.title}>{s.activity_name}</span>
                    <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status_display}</Badge>
                  </div>
                  <span className={styles.path}>{s.activity_path}</span>
                  <div className={styles.values}>
                    <span className="tnum">{Number(s.previous_progress)}%</span>
                    <span className={styles.arrow}>→</span>
                    <span className={`${styles.newVal} tnum`}>{Number(s.submitted_progress)}%</span>
                  </div>
                  <span className={styles.meta}>
                    by {s.submitted_by_name || "—"} · {formatDate(s.created_at)}
                  </span>
                  {s.note && <p className={styles.note}>“{s.note}”</p>}
                  {s.review_comment && <p className={styles.comment}>Comment: {s.review_comment}</p>}
                </div>
                {stage && (
                  <div className={styles.cardActions}>
                    <Button size="sm" onClick={() => decide(s, stage, "approve")}>Approve</Button>
                    <Button size="sm" variant="secondary" onClick={() => setReject({ sub: s, stage })}>Reject</Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </StateView>

      {reject && (
        <RejectModal
          onClose={() => setReject(null)}
          onReject={async (comment) => { await decide(reject.sub, reject.stage, "reject", comment); setReject(null); }}
        />
      )}
    </div>
  );
}

function RejectModal({ onClose, onReject }: { onClose: () => void; onReject: (comment: string) => Promise<void> }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!comment.trim()) { setError("A comment is required."); return; }
    setBusy(true);
    setError(null);
    try {
      await onReject(comment);
    } catch {
      setError("Couldn't reject.");
      setBusy(false);
    }
  }

  return (
    <Modal open title="Reject submission" onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="reject-form" disabled={busy}>{busy ? "Rejecting…" : "Reject"}</Button>
        </>
      }>
      <form id="reject-form" onSubmit={submit} className={styles.form}>
        <label className={styles.label} htmlFor="reject-comment">Reason (required)</label>
        <textarea id="reject-comment" className={styles.textarea} rows={3} autoFocus
          value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Explain what needs correcting…" />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
