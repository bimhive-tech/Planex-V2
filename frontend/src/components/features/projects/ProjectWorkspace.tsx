"use client";

// Project detail shell: header (back, name, edit) + tab bar. Overview is live;
// the remaining tabs are placeholders until their modules ship.
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { ProjectFormDrawer } from "./ProjectFormDrawer";
import { ProjectOverview } from "./ProjectOverview";
import type { ProjectDetail } from "@/types/project";
import styles from "./projectWorkspace.module.css";

const TABS = ["Overview", "Schedule", "Fieldwork", "Approvals", "Delays", "Reports", "Team"] as const;
type Tab = (typeof TABS)[number];

export function ProjectWorkspace({ project, canManage }: { project: ProjectDetail; canManage: boolean }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("Overview");
  const [editOpen, setEditOpen] = useState(false);

  return (
    <div className={styles.page}>
      <div className={styles.topbar}>
        <Link href="/projects" className={styles.back}>
          <Icon name="chevronDown" size={16} />
          <span>Projects</span>
        </Link>
        {canManage && (
          <Button variant="secondary" size="sm" leadingIcon={<Icon name="edit" size={15} />}
            onClick={() => setEditOpen(true)}>
            Edit
          </Button>
        )}
      </div>

      <header className={styles.head}>
        <h1 className={styles.title}>{project.name}</h1>
        <div className={styles.badges}>
          <Badge tone="info">{project.project_type_display}</Badge>
          {project.is_archived && <Badge tone="neutral">Archived</Badge>}
          {project.location && <span className={styles.location}>{project.location}</span>}
        </div>
      </header>

      <nav className={styles.tabs}>
        {TABS.map((t) => (
          <button
            key={t}
            className={`${styles.tab} ${tab === t ? styles.active : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>

      <div className={styles.content}>
        {tab === "Overview" ? (
          <ProjectOverview project={project} />
        ) : (
          <div className={styles.placeholder}>
            <p className={styles.placeholderTitle}>{tab} — coming soon</p>
            <p className={styles.placeholderText}>This module is on the roadmap.</p>
          </div>
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
