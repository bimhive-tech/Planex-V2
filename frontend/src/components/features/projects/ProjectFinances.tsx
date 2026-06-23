"use client";

// Finances tab — gated by the view-finances permission. Two sub-views:
// Cash Flow (monthly planned/actual grid) and Invoices (مستخلصات). Both feed
// the report. Editing requires the manage-finances permission.
import { useState } from "react";

import { CashFlowPanel } from "./CashFlowPanel";
import { InvoicesPanel } from "./InvoicesPanel";
import styles from "./finances.module.css";

type Sub = "cashflow" | "invoices";

export function ProjectFinances({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const [sub, setSub] = useState<Sub>("cashflow");
  return (
    <div className={styles.wrap}>
      <nav className={styles.subtabs}>
        <button className={`${styles.subtab} ${sub === "cashflow" ? styles.active : ""}`} onClick={() => setSub("cashflow")}>
          Cash Flow
        </button>
        <button className={`${styles.subtab} ${sub === "invoices" ? styles.active : ""}`} onClick={() => setSub("invoices")}>
          Invoices
        </button>
      </nav>
      {sub === "cashflow"
        ? <CashFlowPanel projectId={projectId} canManage={canManage} />
        : <InvoicesPanel projectId={projectId} canManage={canManage} />}
    </div>
  );
}
