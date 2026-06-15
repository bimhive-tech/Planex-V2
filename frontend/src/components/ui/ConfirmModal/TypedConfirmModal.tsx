"use client";

// Destructive confirmation: the user must type an exact phrase (e.g. the company
// name) to enable the confirm button. Used for irreversible deletions.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import styles from "./TypedConfirmModal.module.css";

interface Props {
  open: boolean;
  title: string;
  /** The exact text the user must type to confirm. */
  confirmPhrase: string;
  description: React.ReactNode;
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}

export function TypedConfirmModal({
  open,
  title,
  confirmPhrase,
  description,
  confirmLabel = "Delete",
  onConfirm,
  onClose,
}: Props) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTyped("");
      setError(null);
      setBusy(false);
    }
  }, [open]);

  const matches = typed.trim() === confirmPhrase;

  async function handleConfirm() {
    if (!matches) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err) {
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
          <Button variant="primary" type="button" disabled={!matches || busy} onClick={handleConfirm}>
            {busy ? "Deleting…" : confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.body}>
        <p className={styles.description}>{description}</p>
        <p className={styles.instruction}>
          Type <code className={styles.code}>{confirmPhrase}</code> to confirm.
        </p>
        <input
          className={styles.input}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={confirmPhrase}
          autoFocus
          aria-label="Confirmation text"
        />
        {error && <p className="formError">{error}</p>}
      </div>
    </Modal>
  );
}
