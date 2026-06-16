"use client";

// Assign which zones a member can see. No zones selected = full project access
// (mirrors the rule: grants restrict, absence of grants means everything).
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { api, ApiError } from "@/lib/api";
import styles from "./projectTeam.module.css";

interface Props {
  projectId: string;
  memberId: string;
  memberName: string;
  onClose: () => void;
  onSaved: () => void;
}

export function ScopeAccessModal({ projectId, memberId, memberName, onClose, onSaved }: Props) {
  const [zones, setZones] = useState<{ id: string; name: string }[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<{ id: string; name: string }[]>(`/projects/${projectId}/project-zones/`),
      api.get<{ zone_ids: string[] }>(`/projects/${projectId}/members/${memberId}/scope-access/`),
    ])
      .then(([zs, acc]) => {
        setZones(zs);
        setSelected(new Set(acc.zone_ids));
      })
      .catch(() => setError("Couldn't load access."));
  }, [projectId, memberId]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/projects/${projectId}/members/${memberId}/scope-access/`, { zone_ids: [...selected] });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setBusy(false);
    }
  }

  return (
    <Modal open title={`Access · ${memberName}`} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="button" onClick={save} disabled={busy || zones === null}>{busy ? "Saving…" : "Save access"}</Button>
        </>
      }>
      <div className={styles.form}>
        <p className="formHint">
          {selected.size === 0
            ? "No zones selected — this member can see the whole project."
            : `Restricted to ${selected.size} zone${selected.size === 1 ? "" : "s"}.`}
        </p>
        {error && <p className="formError">{error}</p>}
        {zones === null ? (
          <p className="formHint">Loading zones…</p>
        ) : zones.length === 0 ? (
          <p className="formHint">This project has no zones yet (import a tracker first).</p>
        ) : (
          zones.map((z) => (
            <Checkbox key={z.id} name={`z-${z.id}`} label={z.name}
              checked={selected.has(z.id)} onChange={() => toggle(z.id)} />
          ))
        )}
      </div>
    </Modal>
  );
}
