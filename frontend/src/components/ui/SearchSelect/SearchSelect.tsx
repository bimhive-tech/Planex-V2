"use client";

// Searchable dropdown with checkmarks. Single-select (company) or multi-select
// (roles). Value is always an array of option values for a uniform API.
import { useMemo, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useClickOutside } from "@/hooks/useClickOutside";
import styles from "./SearchSelect.module.css";

export interface Option {
  value: string;
  label: string;
}

interface Props {
  label?: string;
  placeholder?: string;
  options: Option[];
  value: string[];
  onChange: (value: string[]) => void;
  multiple?: boolean;
}

export function SearchSelect({
  label,
  placeholder = "Select…",
  options,
  value,
  onChange,
  multiple = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);

  const filtered = useMemo(
    () => options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())),
    [options, query],
  );
  const selected = options.filter((o) => value.includes(o.value));

  function toggle(val: string) {
    if (multiple) {
      onChange(value.includes(val) ? value.filter((v) => v !== val) : [...value, val]);
    } else {
      onChange([val]);
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className={styles.field} ref={ref}>
      {label && <span className={styles.label}>{label}</span>}
      <button type="button" className={styles.trigger} onClick={() => setOpen((o) => !o)}>
        <span className={styles.triggerContent}>
          {selected.length === 0 && <span className={styles.placeholder}>{placeholder}</span>}
          {multiple
            ? selected.map((o) => (
                <span key={o.value} className={styles.chip}>{o.label}</span>
              ))
            : selected[0] && <span className={styles.single}>{selected[0].label}</span>}
        </span>
        <Icon name="chevronDown" size={16} />
      </button>

      {open && (
        <div className={styles.popover}>
          <input
            className={styles.search}
            placeholder="Search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <div className={styles.options}>
            {filtered.length === 0 && <div className={styles.empty}>No matches</div>}
            {filtered.map((o) => {
              const isSel = value.includes(o.value);
              return (
                <button
                  key={o.value}
                  type="button"
                  className={`${styles.option} ${isSel ? styles.optionSelected : ""}`}
                  onClick={() => toggle(o.value)}
                >
                  <span className={styles.check}>{isSel && <Icon name="check" size={14} />}</span>
                  {o.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
