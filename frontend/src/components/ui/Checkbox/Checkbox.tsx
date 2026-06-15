// Checkbox row: box + label, used for role permissions and role selection.
import type { InputHTMLAttributes } from "react";
import styles from "./Checkbox.module.css";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  description?: string;
}

export function Checkbox({ label, description, id, name, ...rest }: Props) {
  const inputId = id ?? name;
  return (
    <label className={styles.row} htmlFor={inputId}>
      <input id={inputId} name={name} type="checkbox" className={styles.box} {...rest} />
      <span className={styles.text}>
        <span className={styles.label}>{label}</span>
        {description && <span className={styles.description}>{description}</span>}
      </span>
    </label>
  );
}
