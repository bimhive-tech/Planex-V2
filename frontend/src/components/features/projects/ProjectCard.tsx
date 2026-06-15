"use client";

// A project tile for the Hub grid. The card navigates to the project; the action
// buttons (edit/archive/delete) sit on top and don't trigger navigation.
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { formatDate } from "@/lib/format";
import type { ProjectListRow } from "@/types/project";
import styles from "./projectCard.module.css";

interface Props {
  project: ProjectListRow;
  canManage: boolean;
  onEdit: (id: string) => void;
  onArchive: (project: ProjectListRow) => void;
  onDelete: (project: ProjectListRow) => void;
}

export function ProjectCard({ project, canManage, onEdit, onArchive, onDelete }: Props) {
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    fn();
  };

  return (
    <Link href={`/projects/${project.id}`} className={styles.card}>
      {canManage && (
        <div className={styles.actions}>
          <button className={styles.actionBtn} aria-label="Edit project" onClick={stop(() => onEdit(project.id))}>
            <Icon name="edit" size={15} />
          </button>
          <button
            className={styles.actionBtn}
            aria-label={project.is_archived ? "Unarchive" : "Archive"}
            title={project.is_archived ? "Unarchive" : "Archive"}
            onClick={stop(() => onArchive(project))}
          >
            <Icon name="projects" size={15} />
          </button>
          <button className={`${styles.actionBtn} ${styles.danger}`} aria-label="Delete project" onClick={stop(() => onDelete(project))}>
            <Icon name="trash" size={15} />
          </button>
        </div>
      )}

      <span className={styles.chip} aria-hidden="true">
        <Icon name="projects" size={20} />
      </span>
      <h3 className={styles.name}>{project.name}</h3>
      <p className={styles.location}>{project.location || "—"}</p>

      <div className={styles.badges}>
        <Badge tone="info">{project.project_type_display}</Badge>
        {project.is_archived && <Badge tone="neutral">Archived</Badge>}
      </div>

      <div className={styles.footer}>
        <span>
          {project.planned_start ? formatDate(project.planned_start) : "—"}
          {" → "}
          {project.planned_finish ? formatDate(project.planned_finish) : "—"}
        </span>
      </div>
    </Link>
  );
}
