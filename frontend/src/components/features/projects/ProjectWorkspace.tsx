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
import { P6ExportButton } from "./P6ExportButton";
import { ProjectFormDrawer } from "./ProjectFormDrawer";
import { ProjectOverview } from "./ProjectOverview";
import { ProjectSchedule } from "./ProjectSchedule";
import { ProjectTeam } from "./ProjectTeam";
import { ProjectApprovals } from "./ProjectApprovals";
import { ProjectDelays } from "./ProjectDelays";
import { ProjectFinances } from "./ProjectFinances";
import { ProjectSubmittals } from "./ProjectSubmittals";
import { ProjectReports } from "./ProjectReports";
import { ProjectReportButton } from "./ProjectReportButton";
import type { ProgressBreakdown, ProjectDetail, ProjectPerms } from "@/types/project";
import styles from "./projectWorkspace.module.css";

export interface ProjectStats {
  overall: number;
  breakdown: ProgressBreakdown;
}

type Tab = "Overview" | "Schedule" | "Team" | "Areas of Concern" | "Finances" | "Submittals" | "Reports" | "Approvals";

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
  // Overview/Team are always visible (opening the project at all already implies
  // base view access); every other tab shows only if the user's COMPANY role
  // grants that module. Least privilege: members without a module's permission
  // never see its tab.
  const showApprovals = perms.review || perms.approve || perms.submit;
  const tabs: Tab[] = [
    "Overview",
    ...(perms.viewSchedule ? (["Schedule"] as Tab[]) : []),
    "Team",
    ...(perms.viewAreasOfConcern ? (["Areas of Concern"] as Tab[]) : []),
    ...(perms.viewFinances ? (["Finances"] as Tab[]) : []),
    ...(perms.viewSubmittals ? (["Submittals"] as Tab[]) : []),
    ...(perms.exportReports ? (["Reports"] as Tab[]) : []),
    ...(showApprovals ? (["Approvals"] as Tab[]) : []),
  ];
  const [tab, setTab] = useState<Tab>(tabs[0] ?? "Overview");
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
        <div className={styles.topActions}>
          {perms.exportReports && <P6ExportButton projectId={project.id} />}
          <ProjectReportButton projectId={project.id} />
          {canManage && (
            <Button variant="secondary" size="sm" leadingIcon={<Icon name="edit" size={15} />}
              onClick={() => setEditOpen(true)}>
              Edit Project
            </Button>
          )}
        </div>
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
          <ProjectSchedule projectId={project.id} canManage={canManage} canSubmit={perms.submit} canDeletePhotos={perms.deletePhotos} onStatsChange={setStats} />
        )}
        {tab === "Team" && <ProjectTeam projectId={project.id} canManage={canManage} />}
        {tab === "Areas of Concern" && <ProjectDelays projectId={project.id} canManage={perms.manageAreasOfConcern} />}
        {tab === "Finances" && <ProjectFinances projectId={project.id} canManage={perms.manageFinances} />}
        {tab === "Submittals" && <ProjectSubmittals projectId={project.id} canManage={perms.manageSubmittals} />}
        {tab === "Reports" && <ProjectReports projectId={project.id} canManage={perms.exportReports} />}
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
