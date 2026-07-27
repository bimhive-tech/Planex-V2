"use client";

// Text input + optional file attach(es). Enter sends, Shift+Enter newlines.
import { useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import styles from "./ai.module.css";

interface Props {
  disabled: boolean;
  onSend: (content: string, files: File[]) => void;
}

export function MessageInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function submit() {
    const content = value.trim();
    if (!content && files.length === 0) return;
    onSend(content, files);
    setValue("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  return (
    <div className={styles.inputBar}>
      {files.length > 0 && (
        <div className={styles.filePreviewRow}>
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} className={styles.filePreview}>
              <Icon name="paperclip" size={14} />
              <span>{f.name}</span>
              <button type="button" onClick={() => removeFile(i)} aria-label={`Remove ${f.name}`}>
                <Icon name="close" size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className={styles.inputRow}>
        <button
          type="button"
          className={styles.attachBtn}
          aria-label="Attach files"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
        >
          <Icon name="paperclip" size={18} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          accept=".xlsx,.xlsm,.pdf,.md,.txt"
          onChange={(e) => setFiles((prev) => [...prev, ...Array.from(e.target.files ?? [])])}
        />
        <textarea
          className={styles.textarea}
          placeholder="Ask about a project, request insights, or attach files to import…"
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
          disabled={disabled || (!value.trim() && files.length === 0)}
          onClick={submit}
        >
          <Icon name="send" size={18} />
        </button>
      </div>
    </div>
  );
}
