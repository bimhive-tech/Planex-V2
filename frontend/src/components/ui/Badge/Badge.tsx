// Pill status badge — light fill + saturated text (style.md status table).
import styles from "./Badge.module.css";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

interface Props {
  tone?: Tone;
  children: React.ReactNode;
}

export function Badge({ tone = "neutral", children }: Props) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}
