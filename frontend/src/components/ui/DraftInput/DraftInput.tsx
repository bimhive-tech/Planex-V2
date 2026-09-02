// Bare input that holds what you type locally and commits once, on blur/Enter.
import { useState } from "react";
import type { InputHTMLAttributes } from "react";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  value: string | number;
  /** Called once per edit, with the finished value — not once per keystroke. */
  onCommit: (value: string) => void;
  /** Reject a value instead of committing it (an unparseable number, say). */
  validate?: (value: string) => boolean;
}

/**
 * An input whose in-progress text is its own, published only when you leave
 * the field or press Enter. Two problems it solves at once:
 *
 * 1. A controlled `value` fighting the caret. `<input type="number">` reports
 *    "" for anything that isn't a valid float — an empty box, or a half-typed
 *    "12." — so committing every keystroke turned Backspace into Number("")
 *    === 0, which clamped the element to the page edge and rewrote the box
 *    under the caret (reported 2026-09-01).
 * 2. One undo entry per keystroke. A 50-character caption used to push 50
 *    history entries and evict every real edit before it.
 *
 * While you aren't editing, the field tracks `value` live — so dragging an
 * element on the canvas still moves the numbers in the inspector.
 */
export function DraftInput({ value, onCommit, validate, onBlur, onKeyDown, ...rest }: Props) {
  const [draft, setDraft] = useState<string | null>(null);

  function commit() {
    if (draft === null) return;
    const next = draft;
    setDraft(null);
    // Silently drop a value the caller can't use — the field snaps back to
    // the real one rather than committing a number nobody typed.
    if (next !== String(value) && (!validate || validate(next))) onCommit(next);
  }

  return (
    <input
      {...rest}
      value={draft ?? String(value ?? "")}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={(e) => { commit(); onBlur?.(e); }}
      onKeyDown={(e) => {
        if (e.key === "Enter") { commit(); (e.target as HTMLInputElement).blur(); }
        // Escape abandons the edit rather than committing it.
        if (e.key === "Escape") { setDraft(null); (e.target as HTMLInputElement).blur(); }
        onKeyDown?.(e);
      }}
    />
  );
}
