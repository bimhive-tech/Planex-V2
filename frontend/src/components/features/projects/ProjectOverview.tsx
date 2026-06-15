// Project Overview tab — descriptive details (the live summary/charts arrive with
// the progress modules). Full-width card sections.
import { formatDate } from "@/lib/format";
import type { ProjectDetail } from "@/types/project";
import styles from "./projectOverview.module.css";

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className={styles.row}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value || "—"}</span>
    </div>
  );
}

export function ProjectOverview({ project: p }: { project: ProjectDetail }) {
  return (
    <div className={styles.grid}>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>General</h2>
        <Row label="Type" value={p.project_type_display} />
        <Row label="Location" value={p.location} />
        <Row label="Size" value={p.size_sqm ? `${p.size_sqm} sqm` : ""} />
        <Row label="Description" value={p.description} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Schedule</h2>
        <Row label="Planned start" value={p.planned_start ? formatDate(p.planned_start) : ""} />
        <Row label="Planned finish" value={p.planned_finish ? formatDate(p.planned_finish) : ""} />
        <Row label="Revised finish" value={p.revised_finish ? formatDate(p.revised_finish) : ""} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Client</h2>
        <Row label="Name" value={p.client_name} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Consultant</h2>
        <Row label="Name" value={p.consultant_name} />
        <Row label="Phone" value={p.consultant_phone} />
        <Row label="Email" value={p.consultant_email} />
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Contractor</h2>
        <Row label="Name" value={p.contractor_name} />
        <Row label="Phone" value={p.contractor_phone} />
        <Row label="Email" value={p.contractor_email} />
      </section>

      {p.notes && (
        <section className={`${styles.card} ${styles.full}`}>
          <h2 className={styles.cardTitle}>Notes</h2>
          <p className={styles.notes}>{p.notes}</p>
        </section>
      )}
    </div>
  );
}
