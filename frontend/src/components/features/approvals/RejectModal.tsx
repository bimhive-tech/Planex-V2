"use client";

// Reject-with-reason modal, shared by the per-project Approvals tab and the
// cross-project Approvals inbox. A comment is required to reject.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import styles from "./rejectModal.module.css";

export function RejectModal({ onClose, onReject }: {
  onClose: () => void;
  onReject: (comment: string) => Promise<void>;
}) {
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
