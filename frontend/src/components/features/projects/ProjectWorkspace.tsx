"use client";

// Project detail shell — clean header with a meta strip + status, then the
// Overview. No placeholder tabs: tabs return as their modules (Schedule, etc.)
// ship, so nothing here shows fake data.
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { formatDate } from "@/lib/format";
import { ProjectFormDrawer } from "./ProjectFormDrawer";
import { ProjectOverview } from "./ProjectOverview";
import type { ProjectDetail } from "@/types/project";
import styles from "./projectWorkspace.module.css";

function Meta({ icon, children }: { icon: IconName; children: React.ReactNode }) {
  return (
    <span className={styles.meta}>
      <Icon name={icon} size={15} />
      {children}
    </span>
  );
}

export function ProjectWorkspace({ project, canManage }: { project: ProjectDetail; canManage: boolean }) {
  const router = useRouter();
  const [editOpen, setEditOpen] = useState(false);

  return (
    <div className={styles.page}>
      <div className={styles.topbar}>
        <Link href="/projects" className={styles.back}>
          <Icon name="chevronDown" size={16} />
          <span>Back to Projects</span>
        </Link>
        {canManage && (
          <Button variant="secondary" size="sm" leadingIcon={<Icon name="edit" size={15} />}
            onClick={() => setEditOpen(true)}>
            Edit Project
          </Button>
        )}
      </div>

      <header className={styles.head}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{project.name}</h1>
          <Badge tone={project.is_archived ? "neutral" : "success"}>
            {project.is_archived ? "Archived" : "Active"}
          </Badge>
        </div>
        <div className={styles.metaRow}>
          <Meta icon="projects">{project.project_type_display}</Meta>
          {project.location && <Meta icon="mapPin">{project.location}</Meta>}
          {project.planned_start && <Meta icon="calendar">Start: {formatDate(project.planned_start)}</Meta>}
          {project.planned_finish && <Meta icon="calendar">End: {formatDate(project.planned_finish)}</Meta>}
          {project.code && <Meta icon="hash">{project.code}</Meta>}
        </div>
      </header>

      <ProjectOverview project={project} />

      <ProjectFormDrawer
        open={editOpen}
        projectId={project.id}
        onClose={() => setEditOpen(false)}
        onSaved={() => router.refresh()}
      />
    </div>
  );
}
