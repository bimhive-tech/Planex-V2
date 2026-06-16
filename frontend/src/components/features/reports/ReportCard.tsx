// One generated report: title, project, period, status badge, and actions
// (view/download PDF, edit, delete).
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import type { ReportRow, ReportStatus } from "@/types/report";
import styles from "./reports.module.css";

const STATUS_TONE: Record<ReportStatus, "neutral" | "info" | "success"> = {
  draft: "neutral",
  submitted: "info",
  approved: "success",
};

function fmt(date: string | null): string {
  if (!date) return "—";
  return new Date(date).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

interface Props {
  report: ReportRow;
  canManage: boolean;
  onView: (r: ReportRow) => void;
  onEdit: (id: string) => void;
  onDelete: (r: ReportRow) => void;
}

export function ReportCard({ report, canManage, onView, onEdit, onDelete }: Props) {
  return (
    <article className={styles.card}>
      <div className={styles.cardTop}>
        <h3 className={styles.cardTitle}>{report.title}</h3>
        <Badge tone={STATUS_TONE[report.status]}>{report.status}</Badge>
      </div>

      <div className={styles.cardMeta}>
        <span className={styles.metaItem}><Icon name="projects" size={14} />{report.project_name}</span>
        {report.report_number && (
          <span className={styles.metaItem}><Icon name="hash" size={14} />{report.report_number}</span>
        )}
        <span className={styles.metaItem}>
          <Icon name="calendar" size={14} />{fmt(report.period_start)} – {fmt(report.period_finish)}
        </span>
        {report.template_name && (
          <span className={styles.metaItem}><Icon name="reports" size={14} />{report.template_name}</span>
        )}
      </div>

      <div className={styles.cardActions}>
        <button className={styles.iconBtn} onClick={() => onView(report)} aria-label="View PDF" title="View PDF">
          <Icon name="download" size={16} />
        </button>
        {canManage && (
          <>
            <button className={styles.iconBtn} onClick={() => onEdit(report.id)} aria-label="Edit" title="Edit">
              <Icon name="edit" size={16} />
            </button>
            <button
              className={`${styles.iconBtn} ${styles.danger}`}
              onClick={() => onDelete(report)}
              aria-label="Delete"
              title="Delete"
            >
              <Icon name="trash" size={16} />
            </button>
          </>
        )}
      </div>
    </article>
  );
}
