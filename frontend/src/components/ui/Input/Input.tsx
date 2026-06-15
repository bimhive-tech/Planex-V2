// Labeled text input primitive. Matches style.md form-field styling.
import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import styles from "./Input.module.css";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  required?: boolean;
}

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { label, id, required, className, ...rest },
  ref,
) {
  const inputId = id ?? rest.name;
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={inputId}>
        {label}
        {required && <span className={styles.required}> *</span>}
      </label>
      <input
        ref={ref}
        id={inputId}
        required={required}
        className={[styles.input, className ?? ""].filter(Boolean).join(" ")}
        {...rest}
      />
    </div>
  );
});
