"use client";

// Searchable dropdown with checkmarks. Single-select (e.g. company) or multi-select
// (e.g. roles). The options panel is rendered in a portal with fixed positioning so
// it overlays *above* a scrollable modal instead of being clipped inside it.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import { Icon } from "@/components/ui/Icon";
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

interface Pos {
  left: number;
  width: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

const PANEL_MAX = 300;

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
  const [pos, setPos] = useState<Pos | null>(null);
  const [mounted, setMounted] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const filtered = useMemo(
    () => options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())),
    [options, query],
  );
  const selected = options.filter((o) => value.includes(o.value));

  // Position the portal panel relative to the trigger; flip above if tight below.
  const reposition = () => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    if (spaceBelow < 280 && spaceAbove > spaceBelow) {
      setPos({
        left: rect.left, width: rect.width,
        bottom: window.innerHeight - rect.top + 4,
        maxHeight: Math.min(PANEL_MAX, spaceAbove - 12),
      });
    } else {
      setPos({
        left: rect.left, width: rect.width,
        top: rect.bottom + 4,
        maxHeight: Math.min(PANEL_MAX, spaceBelow - 12),
      });
    }
  };

  useLayoutEffect(() => {
    if (open) reposition();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Keep aligned on scroll/resize; close on outside pointer (trigger + panel aware).
  useEffect(() => {
    if (!open) return;
    const onMove = () => reposition();
    const onDown = (e: MouseEvent | TouchEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || popoverRef.current?.contains(t)) return;
      setOpen(false);
    };
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [open]);

  function toggle(val: string) {
    if (multiple) {
      onChange(value.includes(val) ? value.filter((v) => v !== val) : [...value, val]);
    } else {
      onChange([val]);
      setOpen(false);
      setQuery("");
    }
  }

  const panelStyle = pos
    ? ({
        "--left": `${pos.left}px`,
        "--width": `${pos.width}px`,
        "--max-h": `${pos.maxHeight}px`,
        "--top": pos.top !== undefined ? `${pos.top}px` : "auto",
        "--bottom": pos.bottom !== undefined ? `${pos.bottom}px` : "auto",
      } as CSSProperties)
    : undefined;

  return (
    <div className={styles.field}>
      {label && <span className={styles.label}>{label}</span>}
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.triggerContent}>
          {selected.length === 0 && <span className={styles.placeholder}>{placeholder}</span>}
          {multiple
            ? selected.map((o) => <span key={o.value} className={styles.chip}>{o.label}</span>)
            : selected[0] && <span className={styles.single}>{selected[0].label}</span>}
        </span>
        <Icon name="chevronDown" size={16} />
      </button>

      {open && mounted && pos &&
        createPortal(
          <div ref={popoverRef} className={styles.popover} style={panelStyle}>
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
          </div>,
          document.body,
        )}
    </div>
  );
}
