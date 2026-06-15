// Donut/ring progress chart (SVG). Shows a percentage with a centered label.
import styles from "./ProgressDonut.module.css";

interface Props {
  value: number; // 0–100
  size?: number;
  label?: string;
}

export function ProgressDonut({ value, size = 140, label = "Overall Progress" }: Props) {
  const pct = Math.max(0, Math.min(100, value));
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);

  return (
    <div className={styles.wrap}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="var(--border)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="var(--primary)" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`} className={styles.ring} />
      </svg>
      <div className={styles.center}>
        <span className={styles.pct}>{Math.round(pct)}%</span>
        <span className={styles.label}>{label}</span>
      </div>
    </div>
  );
}
