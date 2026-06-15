"use client";

// Route-segment error boundary so one failed view doesn't white-screen the app.
import { Button } from "@/components/ui/Button";
import styles from "./error.module.css";

export default function DashboardError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className={styles.wrap}>
      <h2 className={styles.title}>Something went wrong</h2>
      <p className={styles.text}>We couldn’t load this page. Please try again.</p>
      <Button variant="secondary" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
