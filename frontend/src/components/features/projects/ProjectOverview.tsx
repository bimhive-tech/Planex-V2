// Project Overview — card-based summary using only real / computed data.
// (Progress %, report rollups, milestones and team arrive with their modules.)
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { ProgressDonut } from "@/components/ui/ProgressDonut";
import type { ProjectDetail } from "@/types/project";
import type { ProjectStats } from "./ProjectWorkspace";
import { MilestonesPanel } from "./MilestonesPanel";
import { ProgressTimeline } from "./ProgressTimeline";
import { ScheduleTimeline } from "./ScheduleTimeline";
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

// Days between the current forecast and the planned finish — positive means
// running late. Falls back to the revised baseline finish when there's no
// separate forecast yet.
function delayDays(planned: string | null, forecast: string | null, revised: string | null): number | null {
  const against = forecast || revised;
  if (!planned || !against) return null;
  const p = new Date(planned).getTime();
  const f = new Date(against).getTime();
  if (Number.isNaN(p) || Number.isNaN(f)) return null;
  return Math.round((f - p) / DAY);
}

function timeline(start: string | null, finish: string | null) {
  if (!start || !finish) return null;
  const s = new Date(start).getTime();
  const f = new Date(finish).getTime();
  const now = Date.now();
  if (Number.isNaN(s) || Number.isNaN(f)) return null;
  const totalDays = Math.max(1, Math.round((f - s) / DAY));
  const months = Math.max(1, Math.round(totalDays / 30.44));
  const elapsed = Math.max(0, Math.round((Math.min(now, f) - s) / DAY));
  const remaining = Math.round((f - now) / DAY);
  const timePct = Math.min(100, Math.round((elapsed / totalDays) * 100));
  return { months, elapsed, remaining, timePct };
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
  const delay = delayDays(p.planned_finish, p.forecast_finish, p.revised_finish);
  const b = stats.breakdown;
  const pct = (n: number) => (b.total ? Math.round((n / b.total) * 100) : 0);
  const daysLeft = t ? t.remaining : null;

  return (
    <div className={styles.page}>
      {/* At-a-glance KPI strip — schedule-focused, not activity counts. */}
      <section className={styles.statStrip}>
        <Stat icon="check" tone="primary" value={`${Math.round(stats.overall)}%`} label="Work done" />
        <Stat icon="flag" tone="success" value={`${pct(b.completed)}%`} label="Completed" />
        <Stat icon="clock" tone="info" value={t ? `${t.timePct}%` : "—"} label="Time elapsed" />
        <Stat
          icon="calendar"
          tone={daysLeft !== null && daysLeft < 0 ? "danger" : "warning"}
          value={daysLeft === null ? "—" : daysLeft < 0 ? "Overdue" : daysLeft.toLocaleString()}
          label={daysLeft !== null && daysLeft < 0 ? "Past end date" : "Days remaining"}
        />
      </section>

      <div className={styles.layout}>
        {/* Left column — the visual, schedule-first content. */}
        <div className={styles.main}>
          <section className={styles.card}>
            <CardHead icon="calendar" title="Timeline" sub="Schedule health at a glance." />
            <ScheduleTimeline start={p.planned_start} finish={p.planned_finish}
              revised={p.revised_finish} progress={stats.overall} />
          </section>

          <section className={styles.card}>
            <CardHead icon="check" title="Progress Summary" sub="How the work breaks down." />
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

          <ProgressTimeline projectId={p.id} />
          <MilestonesPanel projectId={p.id} canManage={canManage} />
        </div>

        {/* Right column — the reference details and contacts. */}
        <div className={styles.side}>
          <section className={styles.card}>
            <CardHead icon="projects" title="Project Details" sub="Key information for this project." />
            <Row label="Client">{p.client_name || "—"}</Row>
            <Row label="Budget">{formatMoney(p.budget, p.currency)}</Row>
            <Row label="Contract value">{formatMoney(p.contract_value, p.currency)}</Row>
            <Row label="Revised amount">{formatMoney(p.revised_amount, p.currency)}</Row>
            <Row label="Approved value">{formatMoney(p.approved_value, p.currency)}</Row>
            <Row label="Forecast cost">{formatMoney(p.forecast_cost, p.currency)}</Row>
            <Row label="Advance payment">{formatMoney(p.advance_payment, p.currency)}</Row>
            <Row label="Size">{p.size_sqm ? `${Number(p.size_sqm).toLocaleString()} sqm` : "—"}</Row>
            <Row label="Duration">{t ? `${t.months} months` : "—"}</Row>
            <Row label="EOT">{p.eot_days ? `${p.eot_days} days` : "—"}</Row>
            <Row label="Forecast finish">{p.forecast_finish ? new Date(p.forecast_finish).toLocaleDateString() : "—"}</Row>
            <Row label="Delay">
              {delay === null ? "—" : (
                <Badge tone={delay > 0 ? "danger" : "success"}>
                  {delay > 0 ? `${delay} days late` : delay < 0 ? `${-delay} days ahead` : "On time"}
                </Badge>
              )}
            </Row>
            <Row label="Project delay (calendar days)">
              {p.project_delay_days === null ? "—" : p.project_delay_days}
            </Row>
            <Row label="Status">
              <Badge tone={p.is_archived ? "neutral" : "success"}>{p.is_archived ? "Archived" : "Active"}</Badge>
            </Row>
            <Row label="Priority">
              <Badge tone={priorityTone(p.priority)}>{p.priority_display}</Badge>
            </Row>
          </section>

          {(p.part_amount || p.part_completion_revised || p.part_forecast_completion || p.part_delay_days !== null) && (
            <section className={styles.card}>
              <CardHead icon="projects" title="Part (Contracted Sub-Scope)" sub="Tracked alongside the whole project." />
              <Row label="Part amount">{formatMoney(p.part_amount, p.currency)}</Row>
              <Row label="Completion (revised baseline)">
                {p.part_completion_revised ? new Date(p.part_completion_revised).toLocaleDateString() : "—"}
              </Row>
              <Row label="Forecasted completion">
                {p.part_forecast_completion ? new Date(p.part_forecast_completion).toLocaleDateString() : "—"}
              </Row>
              <Row label="Delay (calendar days)">{p.part_delay_days === null ? "—" : p.part_delay_days}</Row>
            </section>
          )}

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
            {p.contractor_consultant && (
              <div className={styles.contactGroup}>
                <span className={styles.contactRole}>Contractor&apos;s Consultant</span>
                <Row label="Name">{p.contractor_consultant}</Row>
              </div>
            )}
          </section>

          {(p.description || p.notes) && (
            <section className={styles.card}>
              <CardHead icon="text" title="About" />
              {p.description && <p className={styles.prose}>{p.description}</p>}
              {p.notes && (
                <p className={styles.notes}>
                  <Icon name="flag" size={14} /> {p.notes}
                </p>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
