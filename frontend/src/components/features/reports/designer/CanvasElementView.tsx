"use client";

// One placed element: its visual, the selection outline, eight resize handles,
// and the Canva-style ⋯ menu. Position/size are mm → px via `scale`.
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { RESIZE_HANDLES } from "@/hooks/useCanvasInteraction";
import type { ResizeHandle } from "@/hooks/useCanvasInteraction";
import type { LayoutElement } from "@/lib/reportLayout";
import type { RepeatItem } from "@/lib/reportRepeat";
import type { ReportData } from "@/types/report";
import { ElementPreview } from "./ElementPreview";
import styles from "./designer.module.css";

export type ElementAction = "duplicate" | "delete" | "forward" | "backward";

interface Props {
  el: LayoutElement;
  scale: number;
  selected: boolean;
  /** Master elements are shown behind page content and aren't editable here. */
  ghost?: boolean;
  onSelect: (id: string) => void;
  onStartMove: (e: React.PointerEvent, el: LayoutElement) => void;
  onStartResize: (e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) => void;
  onStartRotate?: (e: React.PointerEvent, el: LayoutElement) => void;
  onAction: (action: ElementAction, id: string) => void;
  /** Present only in the report-level "Customize" tab. */
  liveData?: ReportData | null;
  pinnedItem?: RepeatItem | RepeatItem[] | null;
}

export function CanvasElementView({
  el, scale, selected, ghost, onSelect, onStartMove, onStartResize, onStartRotate, onAction, liveData, pinnedItem,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  const style: React.CSSProperties = {
    left: `${el.x * scale}px`,
    top: `${el.y * scale}px`,
    width: `${el.w * scale}px`,
    height: `${el.h * scale}px`,
    zIndex: el.z,
    transform: el.rotation ? `rotate(${el.rotation}deg)` : undefined,
  };

  if (ghost) {
    return (
      <div className={`${styles.element} ${styles.elementGhost}`} style={style} aria-hidden="true">
        <ElementPreview el={el} liveData={liveData} pinnedItem={pinnedItem} />
      </div>
    );
  }

  return (
    <div
      data-canvas-element
      className={`${styles.element} ${selected ? styles.elementSelected : ""}`}
      style={style}
      onPointerDown={(e) => {
        // Left button only — right-click should not start a drag.
        if (e.button !== 0) return;
        onSelect(el.id);
        onStartMove(e, el);
      }}
      role="button"
      tabIndex={0}
      aria-label={`${el.type} element`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(el.id);
        }
      }}
    >
      <ElementPreview el={el} liveData={liveData} pinnedItem={pinnedItem} />

      {selected && (
        <>
          {RESIZE_HANDLES.map((h) => (
            <span
              key={h}
              className={`${styles.handle} ${styles[`handle_${h}`]}`}
              onPointerDown={(e) => {
                if (e.button !== 0) return;
                onStartResize(e, el, h);
              }}
            />
          ))}

          {onStartRotate && (
            <span
              className={styles.rotateHandleStem}
              aria-hidden="true"
            >
              <span
                className={styles.rotateHandle}
                role="button"
                aria-label="Rotate element"
                onPointerDown={(e) => {
                  if (e.button !== 0) return;
                  onStartRotate(e, el);
                }}
              >
                <Icon name="refresh" size={11} />
              </span>
            </span>
          )}

          <div className={styles.elementMenu} ref={menuRef}>
            <button
              type="button"
              className={styles.menuTrigger}
              aria-label="Element options"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((v) => !v);
              }}
            >
              ⋯
            </button>
            {menuOpen && (
              <div className={styles.menuPopover} onPointerDown={(e) => e.stopPropagation()}>
                <button type="button" onClick={() => { onAction("duplicate", el.id); setMenuOpen(false); }}>
                  <Icon name="copy" size={14} /> Duplicate
                </button>
                <button type="button" onClick={() => { onAction("forward", el.id); setMenuOpen(false); }}>
                  <Icon name="chevronDown" size={14} className={styles.flipUp} /> Bring forward
                </button>
                <button type="button" onClick={() => { onAction("backward", el.id); setMenuOpen(false); }}>
                  <Icon name="chevronDown" size={14} /> Send backward
                </button>
                <button
                  type="button"
                  className={styles.menuDanger}
                  onClick={() => { onAction("delete", el.id); setMenuOpen(false); }}
                >
                  <Icon name="trash" size={14} /> Delete
                </button>
              </div>
            )}
          </div>

          <span className={styles.sizeBadge}>
            {Math.round(el.w)} × {Math.round(el.h)} mm
          </span>
        </>
      )}
    </div>
  );
}
