"use client";

// Project-detail "Report" action: pick one of the project's reports in a popup
// and open/download its PDF (or jump to the Report Builder).
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, type Paginated } from "@/lib/api";
import { API_BASE, ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import type { ReportRow } from "@/types/report";
import styles from "./reportPicker.module.css";

export function ProjectReportButton({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" size="sm" leadingIcon={<Icon name="download" size={15} />} onClick={() => setOpen(true)}>
        Report PDF
      </Button>
      {open && <ReportPicker projectId={projectId} onClose={() => setOpen(false)} />}
    </>
  );
}

function ReportPicker({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<ReportRow>>(`/reports/?project=${projectId}`),
    [projectId],
  );
  const reports = data?.results ?? [];

  return (
    <Modal open title="Project reports" onClose={onClose}
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      <StateView
        loading={loading}
        error={error}
        isEmpty={reports.length === 0}
        emptyTitle="No reports for this project"
        emptyText="Create one from the Reports area."
        onRetry={reload}
      >
        <ul className={styles.list}>
          {reports.map((r) => (
            <li key={r.id} className={styles.row}>
              <Link href={`${ROUTES.reports}/${r.id}`} className={styles.name} onClick={onClose}>
                {r.title}{r.report_number ? ` (${r.report_number})` : ""}
              </Link>
              <button className={styles.dl} onClick={() => window.open(`${API_BASE}/reports/${r.id}/pdf/`, "_blank", "noopener")}>
                <Icon name="download" size={15} /> PDF
              </button>
            </li>
          ))}
        </ul>
      </StateView>
    </Modal>
  );
}
