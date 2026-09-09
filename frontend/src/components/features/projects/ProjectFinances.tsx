"use client";

// Finances tab — gated by the view-finances permission. Two sub-views:
// Cash Flow (monthly planned/actual grid) and Invoices (مستخلصات). Both feed
// the report. Editing requires the manage-finances permission.
import { useState } from "react";

import { CashFlowPanel } from "./CashFlowPanel";
import { DashboardImport } from "./DashboardImport";
import { InvoicesPanel } from "./InvoicesPanel";
import { ProjectCostPerformance } from "./ProjectCostPerformance";
import styles from "./finances.module.css";

type Sub = "cashflow" | "invoices" | "cost";

export function ProjectFinances({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const [sub, setSub] = useState<Sub>("cashflow");
  // Bumped after an import so the panel on screen refetches — one upload
  // rewrites the cash flow AND the invoices, so whichever is showing is stale.
  const [reloadKey, setReloadKey] = useState(0);
  return (
    <div className={styles.wrap}>
      {canManage && (
        <DashboardImport projectId={projectId} onImported={() => setReloadKey((k) => k + 1)} />
      )}
      <nav className={styles.subtabs}>
        <button className={`${styles.subtab} ${sub === "cashflow" ? styles.active : ""}`} onClick={() => setSub("cashflow")}>
          Cash Flow
        </button>
        <button className={`${styles.subtab} ${sub === "invoices" ? styles.active : ""}`} onClick={() => setSub("invoices")}>
          Invoices
        </button>
        <button className={`${styles.subtab} ${sub === "cost" ? styles.active : ""}`} onClick={() => setSub("cost")}>
          Schedule Cost
        </button>
      </nav>
      {sub === "cashflow" && <CashFlowPanel key={reloadKey} projectId={projectId} canManage={canManage} />}
      {sub === "invoices" && <InvoicesPanel key={reloadKey} projectId={projectId} canManage={canManage} />}
      {sub === "cost" && <ProjectCostPerformance projectId={projectId} />}
    </div>
  );
}
