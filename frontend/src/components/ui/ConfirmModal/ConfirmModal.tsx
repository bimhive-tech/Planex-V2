"use client";

// Confirmation for a destructive action, naming what is about to go (register
// item D4). A real dialog rather than window.confirm: the browser's own popup
// takes a single string, which is too little room to spell out consequences a
// user can't otherwise see — an import taking its activities, scopes and
// milestones with it, and changing every report that reads it.
//
// Its sibling TypedConfirmModal additionally makes the user type an exact
// phrase; that friction is right for deleting a whole company, and wrong for
// "I uploaded the wrong file".
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import styles from "./ConfirmModal.module.css";

interface Props {
  open: boolean;
  title: string;
  /** What is about to happen, in the user's terms. */
  description: React.ReactNode;
  /** The specific things that go with it — rendered as a list so a reader can
   * count them rather than parse a sentence. Omit when there is nothing
   * beyond the thing itself. */
  consequences?: React.ReactNode[];
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}

export function ConfirmModal({
  open, title, description, consequences, confirmLabel = "Delete", onConfirm, onClose,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      setBusy(false);
    }
  }, [open]);

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      // Stay open on failure: closing would hide the reason and leave the user
      // unsure whether the thing was deleted.
      setError(err instanceof Error ? err.message : "Action failed.");
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="button" disabled={busy} onClick={handleConfirm}>
            {busy ? "Working…" : confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.body}>
        <p className={styles.description}>{description}</p>
        {!!consequences?.length && (
          <ul className={styles.consequences}>
            {consequences.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        )}
        <p className={styles.irreversible}>This can&rsquo;t be undone.</p>
        {error && <p className="formError">{error}</p>}
      </div>
    </Modal>
  );
}
