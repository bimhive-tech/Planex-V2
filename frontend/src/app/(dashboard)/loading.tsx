// Generic skeleton fallback for dashboard route segments — shown while a
// page's server data resolves, so navigations never flash an empty screen.
import { Skeleton } from "@/components/ui/Skeleton";
import styles from "./loading.module.css";

export default function DashboardLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading">
      <div className={styles.head}>
        <Skeleton width="240px" height="28px" />
        <Skeleton width="160px" height="16px" />
      </div>
      <div className={styles.strip}>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} height="76px" radius="var(--radius-md)" />
        ))}
      </div>
      <div className={styles.grid}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} height="150px" radius="var(--radius-md)" />
        ))}
      </div>
    </div>
  );
}
