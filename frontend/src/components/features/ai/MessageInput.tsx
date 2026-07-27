"use client";

// Text input + optional single file attach. Enter sends, Shift+Enter newlines.
import { useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import styles from "./ai.module.css";

interface Props {
  disabled: boolean;
  onSend: (content: string, file: File | null) => void;
}

export function MessageInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function submit() {
    const content = value.trim();
    if (!content && !file) return;
    onSend(content, file);
    setValue("");
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <div className={styles.inputBar}>
      {file && (
        <div className={styles.filePreview}>
          <Icon name="paperclip" size={14} />
          <span>{file.name}</span>
          <button type="button" onClick={() => setFile(null)} aria-label="Remove file">
            <Icon name="close" size={12} />
          </button>
        </div>
      )}
      <div className={styles.inputRow}>
        <button
          type="button"
          className={styles.attachBtn}
          aria-label="Attach a file"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
        >
          <Icon name="paperclip" size={18} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          accept=".xlsx,.xlsm,.pdf,.md,.txt"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <textarea
          className={styles.textarea}
          placeholder="Ask about a project, request insights, or attach a file to import…"
          value={value}
          disabled={disabled}
          rows={1}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          className={styles.sendBtn}
          aria-label="Send"
          disabled={disabled || (!value.trim() && !file)}
          onClick={submit}
        >
          <Icon name="send" size={18} />
        </button>
      </div>
    </div>
  );
}
