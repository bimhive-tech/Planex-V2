"use client";

// Accessible modal dialog: backdrop, centered panel, Escape to close, scroll lock.
import { useEffect } from "react";

import { Icon } from "@/components/ui/Icon";
import styles from "./Modal.module.css";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Panel width on tablet+: "md" (default ~480px) or "lg" (~960px). */
  size?: "md" | "lg";
}

export function Modal({ open, title, onClose, children, footer, size = "md" }: Props) {
  useEffect(() => {
    if (!open) return;
    // Lock background scroll while open. Note: clicking the backdrop does NOT
    // close the modal (avoids accidental data loss) — only the X button does.
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className={styles.backdrop} role="presentation">
      <div
        className={`${styles.panel} ${size === "lg" ? styles.lg : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button className={styles.close} onClick={onClose} aria-label="Close">
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className={styles.body}>{children}</div>
        {footer && <footer className={styles.footer}>{footer}</footer>}
      </div>
    </div>
  );
}
