// Project Overview — card-based summary using only real / computed data.
// (Progress %, report rollups, milestones and team arrive with their modules.)
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { formatDate } from "@/lib/format";
import type { ProjectDetail } from "@/types/project";
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

export function ProjectOverview({ project: p }: { project: ProjectDetail }) {
  const t = timeline(p.planned_start, p.planned_finish);

  return (
    <div className={styles.grid}>
      {/* Project details */}
      <section className={styles.card}>
        <header className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Project Details</h2>
          <p className={styles.cardSub}>Key information for this project.</p>
        </header>
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
        <header className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Timeline</h2>
          <p className={styles.cardSub}>Schedule and elapsed time.</p>
        </header>
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
        <header className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Contacts</h2>
          <p className={styles.cardSub}>Consultant and contractor.</p>
        </header>
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
          <header className={styles.cardHead}>
            <h2 className={styles.cardTitle}>About</h2>
          </header>
          {p.description && <p className={styles.prose}>{p.description}</p>}
          {p.notes && (
            <p className={styles.notes}>
              <Icon name="flag" size={14} /> {p.notes}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
