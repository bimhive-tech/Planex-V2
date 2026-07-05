"use client";

// Assign which parts of the project a member can see, using the same hierarchical
// selector as the Report Builder (zones/areas/phases/activities). No selection =
// full project access (grants restrict; absence of grants means everything).
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { ScopeTree } from "@/components/features/reports/ScopeTree";
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
  const [selected, setSelected] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ scope_ids: string[] }>(`/projects/${projectId}/members/${memberId}/scope-access/`)
      .then((acc) => setSelected(acc.scope_ids ?? []))
      .catch(() => setError("Couldn't load access."))
      .finally(() => setReady(true));
  }, [projectId, memberId]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/projects/${projectId}/members/${memberId}/scope-access/`, { scope_ids: selected });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save access.");
      setBusy(false);
    }
  }

  return (
    <Modal open title={`Scope access · ${memberName}`} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="button" onClick={save} disabled={busy || !ready}>{busy ? "Saving…" : "Save access"}</Button>
        </>
      }>
      <div className={styles.form}>
        <p className="formHint">
          {selected.length === 0
            ? "Nothing selected — this member can see the whole project."
            : `Restricted to ${selected.length} selected part${selected.length === 1 ? "" : "s"} (and everything under them).`}
        </p>
        {error && <p className="formError">{error}</p>}
        {ready ? <ScopeTree projectId={projectId} selectedIds={selected} onToggle={toggle} canManage />
               : <p className="formHint">Loading…</p>}
      </div>
    </Modal>
  );
}
