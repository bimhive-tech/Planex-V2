// Native select primitive styled to match inputs (style.md form fields).
import { forwardRef } from "react";
import type { SelectHTMLAttributes } from "react";
import styles from "./Select.module.css";

interface Option {
  value: string;
  label: string;
}

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: Option[];
}

export const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { label, options, id, name, className, ...rest },
  ref,
) {
  const selectId = id ?? name;
  return (
    <div className={styles.field}>
      {label && (
        <label className={styles.label} htmlFor={selectId}>
          {label}
        </label>
      )}
      <select
        ref={ref}
        id={selectId}
        name={name}
        className={[styles.select, className ?? ""].filter(Boolean).join(" ")}
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
});
