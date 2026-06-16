// Renders a single config control (text / number / color / toggle / select)
// for the Template Builder, driven by a BuilderField schema entry.
import { Checkbox } from "@/components/ui/Checkbox";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { BuilderField as Field } from "@/lib/reportTemplate";
import styles from "./builder.module.css";

interface Props {
  field: Field;
  value: unknown;
  onChange: (value: unknown) => void;
}

export function BuilderField({ field, value, onChange }: Props) {
  if (field.type === "toggle") {
    return (
      <div className={styles.toggleField}>
        <Checkbox
          name={field.path}
          label={field.label}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
      </div>
    );
  }

  if (field.type === "color") {
    const hex = typeof value === "string" ? value : "#000000";
    return (
      <div className={styles.field}>
        <span className={styles.fieldLabel}>{field.label}</span>
        <div className={styles.colorRow}>
          <input className={styles.swatch} type="color" value={hex} onChange={(e) => onChange(e.target.value)} aria-label={field.label} />
          <input className={styles.hex} type="text" value={hex} onChange={(e) => onChange(e.target.value)} />
        </div>
      </div>
    );
  }

  if (field.type === "select") {
    return (
      <Select
        label={field.label}
        name={field.path}
        options={field.options ?? []}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  if (field.type === "number") {
    return (
      <Input
        label={field.label}
        name={field.path}
        type="number"
        step="0.1"
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
    );
  }

  return (
    <Input
      label={field.label}
      name={field.path}
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
