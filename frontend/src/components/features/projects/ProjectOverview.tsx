// Project Overview — card-based summary using only real / computed data.
// (Progress %, report rollups, milestones and team arrive with their modules.)
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { ProgressDonut } from "@/components/ui/ProgressDonut";
import { formatDate } from "@/lib/format";
import type { ProjectDetail } from "@/types/project";
import type { ProjectStats } from "./ProjectWorkspace";
import { MilestonesPanel } from "./MilestonesPanel";
import { ProgressTimeline } from "./ProgressTimeline";
import styles from "./projectOverview.module.css";

const DAY = 1000 * 60 * 60 * 24;

function priorityTone(p: string): "danger" | "warning" | "neutral" {
  if (p === "high") return "danger";
  if (p === "medium") return "warning";
  return "neutral";
}

function formatMoney(amount: string | null, currency: string): string {
  if (!amount) return "—";
  const n = Number(amount);
  if (Number.isNaN(n)) return "—";
  return `${currency} ${new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(n)}`;
}

function timeline(start: string | null, finish: string | null) {
  if (!start || !finish) return null;
  const s = new Date(start).getTime();
  const f = new Date(finish).getTime();
  const now = Date.now();
  if (Number.isNaN(s) || Number.isNaN(f)) return null;
  const totalDays = Math.max(0, Math.round((f - s) / DAY));
  const months = Math.max(1, Math.round(totalDays / 30.44));
  const elapsed = Math.max(0, Math.round((Math.min(now, f) - s) / DAY));
  const remaining = Math.round((f - now) / DAY);
  return { months, elapsed, remaining };
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{children}</span>
    </div>
  );
}

// Card header with a small leading icon chip — used by every overview card.
function CardHead({ icon, title, sub }: { icon: IconName; title: string; sub?: string }) {
  return (
    <header className={styles.cardHead}>
      <span className={styles.headIcon}>
        <Icon name={icon} size={16} />
      </span>
      <div>
        <h2 className={styles.cardTitle}>{title}</h2>
        {sub && <p className={styles.cardSub}>{sub}</p>}
      </div>
    </header>
  );
}

// Compact at-a-glance metric tile for the KPI strip at the top of the overview.
function Stat({ icon, tone, value, label }: { icon: IconName; tone: string; value: React.ReactNode; label: string }) {
  return (
    <div className={styles.stat}>
      <span className={`${styles.statIcon} ${styles[`accent_${tone}`]}`}>
        <Icon name={icon} size={18} />
      </span>
      <div className={styles.statText}>
        <span className={`${styles.statValue} tnum`}>{value}</span>
        <span className={styles.statLabel}>{label}</span>
      </div>
    </div>
  );
}

function StatusBar({ tone, label, count, pct }: { tone: string; label: string; count: number; pct: number }) {
  return (
    <div className={styles.statusRow}>
      <div className={styles.statusTop}>
        <span className={styles.statusLabel}>{label}</span>
        <span className={`${styles.statusCount} tnum`}>{count}</span>
      </div>
      <div className={styles.statusTrack}>
        <span
          className={`${styles.statusFill} ${styles[`tone_${tone}`]}`}
          style={{ ["--pct" as string]: `${pct}%` }}
        />
      </div>
      <span className={`${styles.statusPct} tnum`}>{pct}%</span>
    </div>
  );
}

export function ProjectOverview({ project: p, stats, canManage }: { project: ProjectDetail; stats: ProjectStats; canManage: boolean }) {
  const t = timeline(p.planned_start, p.planned_finish);
  const b = stats.breakdown;
  const pct = (n: number) => (b.total ? Math.round((n / b.total) * 100) : 0);
  const daysLeft = t ? t.remaining : null;

  return (
    <div className={styles.page}>
      {/* At-a-glance KPI strip */}
      <section className={styles.statStrip}>
        <Stat icon="check" tone="primary" value={`${Math.round(stats.overall)}%`} label="Overall progress" />
        <Stat icon="list" tone="info" value={b.total.toLocaleString()} label="Activities" />
        <Stat icon="flag" tone="success" value={`${pct(b.completed)}%`} label="Completed" />
        <Stat
          icon="clock"
          tone={daysLeft !== null && daysLeft < 0 ? "danger" : "warning"}
          value={daysLeft === null ? "—" : daysLeft < 0 ? "Overdue" : daysLeft.toLocaleString()}
          label={daysLeft !== null && daysLeft < 0 ? "Past end date" : "Days remaining"}
        />
      </section>

      <div className={styles.grid}>
      {/* Progress summary (rolled up from the Schedule activities) */}
      <section className={`${styles.card} ${styles.wide}`}>
        <CardHead icon="check" title="Progress Summary" sub={`Rolled up from ${b.total} activities.`} />
        {b.total > 0 ? (
          <div className={styles.progressLayout}>
            <ProgressDonut value={stats.overall} />
            <div className={styles.statusBars}>
              <StatusBar tone="success" label="Completed" count={b.completed} pct={pct(b.completed)} />
              <StatusBar tone="warning" label="In Progress" count={b.in_progress} pct={pct(b.in_progress)} />
              <StatusBar tone="neutral" label="Not Started" count={b.not_started} pct={pct(b.not_started)} />
            </div>
          </div>
        ) : (
          <div className={styles.progressBody}>
            <ProgressDonut value={stats.overall} />
            <p className={styles.progressNote}>
              Add activities in the Schedule tab — or import an Excel tracker — to start tracking progress.
            </p>
          </div>
        )}
      </section>

      {/* Project details */}
      <section className={styles.card}>
        <CardHead icon="projects" title="Project Details" sub="Key information for this project." />
        <Row label="Client">{p.client_name || "—"}</Row>
        <Row label="Budget">{formatMoney(p.budget, p.currency)}</Row>
        <Row label="Size">{p.size_sqm ? `${Number(p.size_sqm).toLocaleString()} sqm` : "—"}</Row>
        <Row label="Status">
          <Badge tone={p.is_archived ? "neutral" : "success"}>{p.is_archived ? "Archived" : "Active"}</Badge>
        </Row>
        <Row label="Priority">
          <Badge tone={priorityTone(p.priority)}>{p.priority_display}</Badge>
        </Row>
      </section>

      {/* Timeline (computed) */}
      <section className={styles.card}>
        <CardHead icon="calendar" title="Timeline" sub="Schedule and elapsed time." />
        <Row label="Start date">{p.planned_start ? formatDate(p.planned_start) : "—"}</Row>
        <Row label="End date">{p.planned_finish ? formatDate(p.planned_finish) : "—"}</Row>
        {p.revised_finish && <Row label="Revised finish">{formatDate(p.revised_finish)}</Row>}
        <Row label="Duration">{t ? `${t.months} months` : "—"}</Row>
        <Row label="Days elapsed"><span className="tnum">{t ? t.elapsed : "—"}</span></Row>
        <Row label="Days remaining">
          {t ? (
            t.remaining >= 0 ? <span className="tnum">{t.remaining}</span> : <span className={styles.overdue}>Overdue</span>
          ) : "—"}
        </Row>
      </section>

      {/* Contacts */}
      <section className={styles.card}>
        <CardHead icon="users" title="Contacts" sub="Consultant and contractor." />
        <div className={styles.contactGroup}>
          <span className={styles.contactRole}>Consultant</span>
          <Row label="Name">{p.consultant_name || "—"}</Row>
          {p.consultant_phone && <Row label="Phone">{p.consultant_phone}</Row>}
          {p.consultant_email && <Row label="Email">{p.consultant_email}</Row>}
        </div>
        <div className={styles.contactGroup}>
          <span className={styles.contactRole}>Contractor</span>
          <Row label="Name">{p.contractor_name || "—"}</Row>
          {p.contractor_phone && <Row label="Phone">{p.contractor_phone}</Row>}
          {p.contractor_email && <Row label="Email">{p.contractor_email}</Row>}
        </div>
      </section>

      {(p.description || p.notes) && (
        <section className={`${styles.card} ${styles.full}`}>
          <CardHead icon="text" title="About" />
          {p.description && <p className={styles.prose}>{p.description}</p>}
          {p.notes && (
            <p className={styles.notes}>
              <Icon name="flag" size={14} /> {p.notes}
            </p>
          )}
        </section>
      )}

      <ProgressTimeline projectId={p.id} />
      <MilestonesPanel projectId={p.id} canManage={canManage} />
      </div>
    </div>
  );
}
