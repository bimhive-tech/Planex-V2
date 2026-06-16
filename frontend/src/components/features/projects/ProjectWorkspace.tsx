"use client";

// Project detail shell — header (meta strip + status), tabs, and the active tab.
// Overall progress is shared state so editing on Schedule updates the Overview donut.
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
import { ProjectSchedule } from "./ProjectSchedule";
import { ProjectTeam } from "./ProjectTeam";
import { ProjectApprovals } from "./ProjectApprovals";
import type { ProgressBreakdown, ProjectDetail, ProjectPerms } from "@/types/project";
import styles from "./projectWorkspace.module.css";

export interface ProjectStats {
  overall: number;
  breakdown: ProgressBreakdown;
}

type Tab = "Overview" | "Schedule" | "Team" | "Approvals";

function Meta({ icon, children }: { icon: IconName; children: React.ReactNode }) {
  return (
    <span className={styles.meta}>
      <Icon name={icon} size={15} />
      {children}
    </span>
  );
}

export function ProjectWorkspace({ project, canManage, perms }: { project: ProjectDetail; canManage: boolean; perms: ProjectPerms }) {
  const router = useRouter();
  const showApprovals = perms.review || perms.approve || perms.submit;
  const tabs: Tab[] = ["Overview", "Schedule", "Team", ...(showApprovals ? (["Approvals"] as Tab[]) : [])];
  const [tab, setTab] = useState<Tab>("Overview");
  const [editOpen, setEditOpen] = useState(false);
  const [stats, setStats] = useState<ProjectStats>({
    overall: project.overall_progress,
    breakdown: project.progress_breakdown,
  });

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

      <nav className={styles.tabs}>
        {tabs.map((t) => (
          <button key={t} className={`${styles.tab} ${tab === t ? styles.active : ""}`} onClick={() => setTab(t)}>
            {t}
            {t === "Approvals" && project.open_submission_count > 0 && (
              <span className={styles.tabBadge}>{project.open_submission_count}</span>
            )}
          </button>
        ))}
      </nav>

      <div className={styles.content}>
        {tab === "Overview" && <ProjectOverview project={project} stats={stats} canManage={canManage} />}
        {tab === "Schedule" && (
          <ProjectSchedule projectId={project.id} canManage={canManage} canSubmit={perms.submit} onStatsChange={setStats} />
        )}
        {tab === "Team" && <ProjectTeam projectId={project.id} canManage={canManage} />}
        {tab === "Approvals" && (
          <ProjectApprovals projectId={project.id} perms={perms} onChanged={() => router.refresh()} />
        )}
      </div>

      <ProjectFormDrawer
        open={editOpen}
        projectId={project.id}
        onClose={() => setEditOpen(false)}
        onSaved={() => router.refresh()}
      />
    </div>
  );
}
