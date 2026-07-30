"use client";

// The paper: guides (margin box, header/footer bands), master elements as
// non-interactive ghosts, then this page's own elements on top.
import { contentBox, pageDimensions } from "@/lib/reportLayout";
import type { LayoutElement, PageDesign } from "@/lib/reportLayout";
import type { ResizeHandle } from "@/hooks/useCanvasInteraction";
import { CanvasElementView } from "./CanvasElementView";
import type { ElementAction } from "./CanvasElementView";
import styles from "./designer.module.css";

interface Props {
  design: PageDesign;
  elements: LayoutElement[];
  masterElements?: LayoutElement[];
  scale: number;
  selectedId: string | null;
  showGuides: boolean;
  onSelect: (id: string | null) => void;
  onStartMove: (e: React.PointerEvent, el: LayoutElement) => void;
  onStartResize: (e: React.PointerEvent, el: LayoutElement, handle: ResizeHandle) => void;
  onAction: (action: ElementAction, id: string) => void;
  /** Drop from the palette — coordinates arrive in mm, already page-relative. */
  onDropSpec?: (specKey: string, xMm: number, yMm: number) => void;
}

export function CanvasPage({
  design, elements, masterElements = [], scale, selectedId, showGuides,
  onSelect, onStartMove, onStartResize, onAction, onDropSpec,
}: Props) {
  const { w, h } = pageDimensions(design);
  const box = contentBox(design);

  return (
    <div
      className={styles.paper}
      style={{
        width: `${w * scale}px`,
        height: `${h * scale}px`,
        background: design.background,
        border: design.show_border ? "1px solid var(--text-primary)" : "1px solid var(--border)",
      }}
      onPointerDown={() => onSelect(null)}
      onDragOver={(e) => {
        if (!onDropSpec) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(e) => {
        if (!onDropSpec) return;
        e.preventDefault();
        const key = e.dataTransfer.getData("text/planex-element");
        if (!key) return;
        const rect = e.currentTarget.getBoundingClientRect();
        onDropSpec(key, (e.clientX - rect.left) / scale, (e.clientY - rect.top) / scale);
      }}
    >
      {showGuides && (
        <>
          <div
            className={styles.guideMargin}
            style={{
              left: `${design.margin_mm * scale}px`,
              top: `${design.margin_mm * scale}px`,
              width: `${Math.max(0, w - design.margin_mm * 2) * scale}px`,
              height: `${Math.max(0, h - design.margin_mm * 2) * scale}px`,
            }}
          />
          {design.show_header && (
            <div
              className={styles.guideBand}
              style={{
                left: `${design.margin_mm * scale}px`,
                top: `${design.margin_mm * scale}px`,
                width: `${Math.max(0, w - design.margin_mm * 2) * scale}px`,
                height: `${design.header_mm * scale}px`,
              }}
            >
              <span>Header · {design.header_mm}mm</span>
            </div>
          )}
          {design.show_footer && (
            <div
              className={styles.guideBand}
              style={{
                left: `${design.margin_mm * scale}px`,
                top: `${(h - design.margin_mm - design.footer_mm) * scale}px`,
                width: `${Math.max(0, w - design.margin_mm * 2) * scale}px`,
                height: `${design.footer_mm * scale}px`,
              }}
            >
              <span>Footer · {design.footer_mm}mm</span>
            </div>
          )}
          <div
            className={styles.guideContent}
            style={{
              left: `${box.x * scale}px`,
              top: `${box.y * scale}px`,
              width: `${box.w * scale}px`,
              height: `${box.h * scale}px`,
            }}
          />
        </>
      )}

      {masterElements.map((el) => (
        <CanvasElementView
          key={`master-${el.id}`}
          el={el}
          scale={scale}
          selected={false}
          ghost
          onSelect={() => {}}
          onStartMove={() => {}}
          onStartResize={() => {}}
          onAction={() => {}}
        />
      ))}

      {[...elements].sort((a, b) => a.z - b.z).map((el) => (
        <CanvasElementView
          key={el.id}
          el={el}
          scale={scale}
          selected={el.id === selectedId}
          onSelect={onSelect}
          onStartMove={onStartMove}
          onStartResize={onStartResize}
          onAction={onAction}
        />
      ))}
    </div>
  );
}
