"use client";

// Read-only lifecycle/audit trail for a single submission: every stage it went
// through (submitted → reviewed → final decision) with who, when, and comments.
// Built from the submission record — no extra fetch.
import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { formatDateTime } from "@/lib/format";
import type { ProjectSubmission } from "@/types/project";
import styles from "./auditTrail.module.css";

type Tone = "neutral" | "success" | "danger" | "info";

interface Step {
  icon: IconName;
  tone: Tone;
  title: string;
  by: string;
  at: string | null;
  comment?: string;
}

// Derive the trail from the submission's stage fields + status.
function buildSteps(s: ProjectSubmission): Step[] {
  const steps: Step[] = [
    {
      icon: "plus", tone: "info", title: "Submitted for review",
      by: s.submitted_by_name || "—", at: s.created_at,
      comment: s.note || undefined,
    },
  ];

  // Review stage (recorded once reviewed_at is set).
  if (s.reviewed_at || ["pending_pm", "reviewer_rejected", "pm_rejected", "accepted"].includes(s.status)) {
    const rejected = s.status === "reviewer_rejected";
    steps.push({
      icon: rejected ? "close" : "check",
      tone: rejected ? "danger" : "success",
      title: rejected ? "Rejected by reviewer" : "Approved by reviewer",
      by: s.reviewed_by_name || "—", at: s.reviewed_at,
      comment: rejected ? s.review_comment || undefined : undefined,
    });
  }

  // Final PM decision.
  if (s.decided_at || ["pm_rejected", "accepted"].includes(s.status)) {
    const accepted = s.status === "accepted";
    steps.push({
      icon: accepted ? "check" : "close",
      tone: accepted ? "success" : "danger",
      title: accepted ? "Accepted (official)" : "Rejected by approver",
      by: s.approved_by_name || "—", at: s.decided_at,
      comment: !accepted ? s.review_comment || undefined : undefined,
    });
  }

  return steps;
}

export function AuditTrailDrawer({ submission, onClose }: {
  submission: ProjectSubmission | null;
  onClose: () => void;
}) {
  const open = submission !== null;
  return (
    <Drawer open={open} title="Audit trail" onClose={onClose}>
      {submission && (
        <div className={styles.body}>
          <div className={styles.summary}>
            <span className={styles.activity}>{submission.activity_name}</span>
            <span className={styles.path}>{submission.activity_path}</span>
            <div className={styles.change}>
              <span className="tnum">{Number(submission.previous_progress)}%</span>
              <span className={styles.arrow}>→</span>
              <span className={`${styles.newVal} tnum`}>{Number(submission.submitted_progress)}%</span>
            </div>
          </div>

          <ol className={styles.timeline}>
            {buildSteps(submission).map((step, i) => (
              <li key={i} className={styles.step}>
                <span className={`${styles.marker} ${styles[`tone_${step.tone}`]}`}>
                  <Icon name={step.icon} size={14} />
                </span>
                <div className={styles.stepBody}>
                  <span className={styles.stepTitle}>{step.title}</span>
                  <span className={styles.stepMeta}>
                    {step.by}{step.at ? ` · ${formatDateTime(step.at)}` : ""}
                  </span>
                  {step.comment && <p className={styles.comment}>“{step.comment}”</p>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Drawer>
  );
}
