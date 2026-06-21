"use client";

// Lightweight Word-like rich text editor (contentEditable + a formatting
// toolbar). Emits HTML; the backend sanitizes it and renders it faithfully into
// the report PDF. styleWithCSS is forced off so the browser emits tags
// (<b>/<i>/<u>/<font>) the PDF renderer understands rather than inline styles.
import { useEffect, useRef } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import styles from "./RichTextEditor.module.css";

interface Props {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
}

const SIZES = [
  { label: "Small", value: "2" },
  { label: "Normal", value: "3" },
  { label: "Large", value: "5" },
  { label: "X-Large", value: "6" },
  { label: "Huge", value: "7" },
];

export function RichTextEditor({ value, onChange, placeholder }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const lastHtml = useRef<string>("");

  // Seed/refresh content only on external changes, so typing never resets the caret.
  useEffect(() => {
    const el = ref.current;
    if (el && value !== lastHtml.current) {
      el.innerHTML = value || "";
      lastHtml.current = value || "";
    }
  }, [value]);

  function emit() {
    const html = ref.current?.innerHTML ?? "";
    lastHtml.current = html;
    onChange(html);
  }

  function exec(command: string, arg?: string) {
    document.execCommand("styleWithCSS", false, "false");
    document.execCommand(command, false, arg);
    ref.current?.focus();
    emit();
  }

  return (
    <div className={styles.editor}>
      <div className={styles.toolbar} role="toolbar" aria-label="Text formatting">
        <ToolButton title="Bold" onClick={() => exec("bold")} label="B" bold />
        <ToolButton title="Italic" onClick={() => exec("italic")} label="I" italic />
        <ToolButton title="Underline" onClick={() => exec("underline")} label="U" underline />
        <span className={styles.sep} />
        <ToolButton icon="list" title="Bullet list" onClick={() => exec("insertUnorderedList")} />
        <ToolButton icon="listOrdered" title="Numbered list" onClick={() => exec("insertOrderedList")} />
        <span className={styles.sep} />
        <ToolButton icon="alignRight" title="Align right" onClick={() => exec("justifyRight")} />
        <ToolButton icon="alignCenter" title="Align center" onClick={() => exec("justifyCenter")} />
        <ToolButton icon="alignLeft" title="Align left" onClick={() => exec("justifyLeft")} />
        <span className={styles.sep} />
        <select className={styles.size} title="Text size" defaultValue="3"
          onChange={(e) => exec("fontSize", e.target.value)}>
          {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <label className={styles.color} title="Text color">
          <Icon name="text" size={15} />
          <input type="color" onChange={(e) => exec("foreColor", e.target.value)} aria-label="Text color" />
        </label>
      </div>

      <div
        ref={ref}
        className={styles.surface}
        contentEditable
        suppressContentEditableWarning
        dir="auto"
        data-placeholder={placeholder}
        onInput={emit}
        onBlur={emit}
      />
    </div>
  );
}

function ToolButton({ icon, title, onClick, label, bold, italic, underline }: {
  icon?: IconName; title: string; onClick: () => void; label?: string;
  bold?: boolean; italic?: boolean; underline?: boolean;
}) {
  const cls = [styles.btn, bold && styles.b, italic && styles.i, underline && styles.u]
    .filter(Boolean).join(" ");
  return (
    <button
      type="button"
      className={cls}
      title={title}
      aria-label={title}
      onMouseDown={(e) => e.preventDefault()} // keep the selection
      onClick={onClick}
    >
      {label ?? (icon && <Icon name={icon} size={16} />)}
    </button>
  );
}
