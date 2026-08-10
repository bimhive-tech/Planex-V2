// One milestone row (status dot, title, date) with optional edit/delete —
// shared by the Overview highlights card and the full Milestones tab.
import { Icon } from "@/components/ui/Icon";
import { formatDate } from "@/lib/format";
import type { Milestone } from "./milestoneShared";
import styles from "./milestones.module.css";

export function MilestoneListItem({ milestone: m, canManage, onEdit, onDelete }: {
  milestone: Milestone; canManage: boolean; onEdit: () => void; onDelete: () => void;
}) {
  return (
    <li className={styles.item}>
      <span className={`${styles.dot} ${styles[`s_${m.status}`]}`} aria-hidden="true">
        {m.status === "completed" && <Icon name="check" size={12} />}
      </span>
      <div className={styles.itemBody}>
        <span className={styles.itemTitle}>{m.title}</span>
        <span className={styles.itemMeta}>
          {m.status_display}
          {m.progress_percent !== null ? ` · ${Math.round(Number(m.progress_percent))}%` : ""}
          {m.date ? ` · ${formatDate(m.date)}` : ""}
        </span>
      </div>
      {canManage && (
        <div className={styles.itemActions}>
          <button className={styles.iconBtn} aria-label="Edit" onClick={onEdit}>
            <Icon name="edit" size={14} />
          </button>
          <button className={styles.iconBtn} aria-label="Delete" onClick={onDelete}>
            <Icon name="trash" size={14} />
          </button>
        </div>
      )}
    </li>
  );
}
