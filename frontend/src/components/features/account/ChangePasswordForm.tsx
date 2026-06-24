"use client";

// Self-service password change. Confirms the current password, validates the
// new one client-side (match + length), and surfaces backend field errors.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import styles from "./account.module.css";

const MIN_LEN = 8;

export function ChangePasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (next.length < MIN_LEN) {
      setError(`New password must be at least ${MIN_LEN} characters.`);
      return;
    }
    if (next !== confirm) {
      setError("New passwords don't match.");
      return;
    }
    setSaving(true);
    try {
      await api.post("/auth/change-password/", { current_password: current, new_password: next });
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change your password. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <Input label="Current password" type="password" name="current" autoComplete="current-password"
        value={current} onChange={(e) => setCurrent(e.target.value)} required />
      <Input label="New password" type="password" name="new" autoComplete="new-password"
        value={next} onChange={(e) => setNext(e.target.value)} required />
      <Input label="Confirm new password" type="password" name="confirm" autoComplete="new-password"
        value={confirm} onChange={(e) => setConfirm(e.target.value)} required />

      {error && <p className={styles.error}>{error}</p>}
      {done && <p className={styles.success}>Your password has been changed.</p>}

      <div className={styles.formActions}>
        <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Change password"}</Button>
      </div>
    </form>
  );
}
