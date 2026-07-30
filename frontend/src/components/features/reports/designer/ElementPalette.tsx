"use client";

// Left sidebar: what you can add, grouped by category. Items can be dragged
// onto the paper (drops where you release) or clicked (lands in the content
// box) — same as Canva's element panel.
import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";
import { ELEMENT_CATALOG } from "@/lib/reportElements";
import styles from "./designer.module.css";

interface Props {
  onAdd: (specKey: string) => void;
}

export function ElementPalette({ onAdd }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>(
    () => Object.fromEntries(ELEMENT_CATALOG.map((c) => [c.key, true])),
  );

  return (
    <aside className={styles.palette} aria-label="Add elements">
      <h2 className={styles.panelTitle}>Add to page</h2>
      <p className={styles.panelHint}>Drag onto the page, or click to place it.</p>

      {ELEMENT_CATALOG.map((category) => (
        <section key={category.key} className={styles.category}>
          <button
            type="button"
            className={styles.categoryHead}
            onClick={() => setOpen((o) => ({ ...o, [category.key]: !o[category.key] }))}
            aria-expanded={open[category.key]}
          >
            <Icon
              name="chevronDown"
              size={14}
              className={open[category.key] ? "" : styles.chevronClosed}
            />
            {category.title}
          </button>

          {open[category.key] && (
            <div className={styles.categoryItems}>
              {category.items.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={styles.paletteItem}
                  title={item.hint ?? item.label}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/planex-element", item.key);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() => onAdd(item.key)}
                >
                  <Icon name={item.icon as IconName} size={16} />
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      ))}
    </aside>
  );
}
