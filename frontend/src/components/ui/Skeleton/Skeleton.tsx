// Shimmering placeholder block for loading states. Sizes come from props as
// dynamic CSS variables so the stylesheet keeps the actual styling.
import styles from "./Skeleton.module.css";

interface Props {
  width?: string;
  height?: string;
  radius?: string;
  className?: string;
}

export function Skeleton({ width = "100%", height = "16px", radius = "var(--radius-sm)", className }: Props) {
  return (
    <span
      className={[styles.skeleton, className ?? ""].filter(Boolean).join(" ")}
      style={{ ["--sk-w" as string]: width, ["--sk-h" as string]: height, ["--sk-r" as string]: radius }}
      aria-hidden="true"
    />
  );
}
