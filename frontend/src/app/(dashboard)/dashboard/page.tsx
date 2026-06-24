// Dashboard landing — a real at-a-glance home: portfolio KPIs, the user's
// projects, and permission-aware quick actions. Server-rendered; all data is
// fetched server-side and degrades gracefully if an endpoint is unavailable.
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { getCurrentUser } from "@/lib/server-auth";
import { getDashboardData } from "@/lib/server-dashboard";
import { Permission } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";
import styles from "./dashboard.module.css";

const PROJECTS_ROUTE = "/projects";
const TODAY_FMT = new Intl.DateTimeFormat("en", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

function Stat({ icon, tone, value, label, href }: {
  icon: IconName; tone: string; value: React.ReactNode; label: string; href?: string;
}) {
  const inner = (
    <>
      <span className={`${styles.statIcon} ${styles[`accent_${tone}`]}`}>
        <Icon name={icon} size={20} />
      </span>
      <div className={styles.statText}>
        <span className={`${styles.statValue} tnum`}>{value}</span>
        <span className={styles.statLabel}>{label}</span>
      </div>
    </>
  );
  return href ? (
    <Link href={href} className={`${styles.stat} ${styles.statLink}`}>{inner}</Link>
  ) : (
    <div className={styles.stat}>{inner}</div>
  );
}

export default async function DashboardPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  const data = await getDashboardData();
  const can = (perm: string) => user.is_platform_admin || user.permissions.includes(perm);
  const canViewProjects = can(Permission.VIEW_PROJECTS) || can(Permission.MANAGE_PROJECTS);
  const archived = Math.max(0, data.projectCount - data.activeCount);

  const actions: { icon: IconName; label: string; desc: string; href: string }[] = [];
  if (canViewProjects) actions.push({ icon: "projects", label: "Projects", desc: "Browse and manage projects", href: PROJECTS_ROUTE });
  if (data.reportCount !== null) actions.push({ icon: "reports", label: "Reports", desc: "Generate and download reports", href: ROUTES.reports });
  actions.push({ icon: "settings", label: "Settings", desc: "Company, users, and roles", href: ROUTES.settings });

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>Welcome back, {user.first_name || user.full_name}</h1>
          <p className={styles.subtitle}>
            {user.company?.name ?? "—"}
            {user.is_platform_admin && <span className={styles.tag}>Platform</span>}
          </p>
        </div>
        <span className={styles.today}>{TODAY_FMT.format(new Date())}</span>
      </header>

      {/* Portfolio KPIs */}
      <section className={styles.statStrip}>
        <Stat icon="projects" tone="primary" value={data.projectCount.toLocaleString()} label="Total projects" href={canViewProjects ? PROJECTS_ROUTE : undefined} />
        <Stat icon="check" tone="success" value={data.activeCount.toLocaleString()} label="Active" />
        <Stat icon="clock" tone="neutral" value={archived.toLocaleString()} label="Archived" />
        {data.reportCount !== null && (
          <Stat icon="reports" tone="info" value={data.reportCount.toLocaleString()} label="Reports" href={ROUTES.reports} />
        )}
      </section>

      {/* The user's projects (or an empty-state CTA) */}
      {canViewProjects && (
        <section className={styles.block}>
          <div className={styles.blockHead}>
            <h2 className={styles.blockTitle}>Your projects</h2>
            {data.projectCount > data.projects.length && (
              <Link href={PROJECTS_ROUTE} className={styles.viewAll}>View all<span className={styles.chevR}><Icon name="chevronDown" size={14} /></span></Link>
            )}
          </div>
          {data.projects.length > 0 ? (
            <div className={styles.projectGrid}>
              {data.projects.slice(0, 6).map((proj) => (
                <Link key={proj.id} href={`${PROJECTS_ROUTE}/${proj.id}`} className={styles.projectCard}>
                  <div className={styles.projectTop}>
                    <span className={styles.projectName}>{proj.name}</span>
                    <Badge tone={proj.is_archived ? "neutral" : "success"}>{proj.is_archived ? "Archived" : "Active"}</Badge>
                  </div>
                  <div className={styles.projectMeta}>
                    <span className={styles.projectMetaItem}><Icon name="projects" size={14} />{proj.project_type_display}</span>
                    {proj.location && <span className={styles.projectMetaItem}><Icon name="mapPin" size={14} />{proj.location}</span>}
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className={styles.empty}>
              <span className={styles.emptyIcon}><Icon name="projects" size={24} /></span>
              <p className={styles.emptyText}>No projects yet.</p>
              <Link href={PROJECTS_ROUTE} className={styles.emptyCta}>Go to Projects</Link>
            </div>
          )}
        </section>
      )}

      {/* Quick navigation */}
      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2 className={styles.blockTitle}>Quick actions</h2>
        </div>
        <div className={styles.actionGrid}>
          {actions.map((a) => (
            <Link key={a.href} href={a.href} className={styles.action}>
              <span className={styles.actionIcon}><Icon name={a.icon} size={18} /></span>
              <div className={styles.actionText}>
                <span className={styles.actionLabel}>{a.label}</span>
                <span className={styles.actionDesc}>{a.desc}</span>
              </div>
              <span className={styles.chevR}><Icon name="chevronDown" size={16} /></span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
