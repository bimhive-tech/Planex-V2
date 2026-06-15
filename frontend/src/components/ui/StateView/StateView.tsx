// Renders the loading / error / empty states for a data view, or its children
// on success. Keeps every list/table consistent (CLAUDE.md §12).
import { Button } from "@/components/ui/Button";
import styles from "./StateView.module.css";

interface Props {
  loading: boolean;
  error: string | null;
  isEmpty: boolean;
  emptyTitle?: string;
  emptyText?: string;
  onRetry?: () => void;
  children: React.ReactNode;
}

export function StateView({
  loading,
  error,
  isEmpty,
  emptyTitle = "Nothing here yet",
  emptyText,
  onRetry,
  children,
}: Props) {
  if (loading) {
    return (
      <div className={styles.center}>
        <span className={styles.spinner} aria-label="Loading" />
      </div>
    );
  }
  if (error) {
    return (
      <div className={styles.center}>
        <p className={styles.errorText}>{error}</p>
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    );
  }
  if (isEmpty) {
    return (
      <div className={styles.center}>
        <p className={styles.emptyTitle}>{emptyTitle}</p>
        {emptyText && <p className={styles.emptyText}>{emptyText}</p>}
      </div>
    );
  }
  return <>{children}</>;
}
