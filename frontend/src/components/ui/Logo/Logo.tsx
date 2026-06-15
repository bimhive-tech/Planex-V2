// Planex wordmark: purple rounded-square mark + label.
import styles from "./Logo.module.css";

interface Props {
  showWordmark?: boolean;
}

export function Logo({ showWordmark = true }: Props) {
  return (
    <div className={styles.logo}>
      <span className={styles.mark} aria-hidden="true">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#fff" strokeWidth="2.2">
          <path d="M4 20V6a2 2 0 0 1 2-2h7l5 5v3" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M8 12h6M8 16h4" strokeLinecap="round" />
        </svg>
      </span>
      {showWordmark && <span className={styles.wordmark}>Planex</span>}
    </div>
  );
}
