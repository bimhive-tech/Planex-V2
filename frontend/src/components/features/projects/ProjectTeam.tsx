"use client";

// Team tab: member cards (avatar, name, their real company role, email) +
// add/remove/edit-access. There's no separate per-project role — everyone's
// role badge is their actual company role from Settings → Roles, read-only
// here. What IS project-specific is scope: which parts of THIS project a
// member can see within whatever modules their company role already grants.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { SearchSelect } from "@/components/ui/SearchSelect";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { ScopeTree } from "@/components/features/reports/ScopeTree";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ProjectMember } from "@/types/project";
import { ScopeAccessModal } from "./ScopeAccessModal";
import styles from "./projectTeam.module.css";

function initials(name: string, email: string) {
  const base = name.trim() || email;
  const parts = base.split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || email[0].toUpperCase();
}

export function ProjectTeam({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectMember[]>(`/projects/${projectId}/members/`),
    [projectId],
  );
  const [addOpen, setAddOpen] = useState(false);
  const [accessFor, setAccessFor] = useState<ProjectMember | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const members = data ?? [];

  async function remove(m: ProjectMember) {
    if (!window.confirm(`Remove ${m.full_name || m.email} from the team?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/members/${m.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't remove member.");
    }
  }

  return (
    <div>
      <div className={styles.head}>
        <span className={styles.muted}>{members.length} {members.length === 1 ? "member" : "members"}</span>
        {canManage && (
          <Button size="sm" leadingIcon={<Icon name="plus" size={16} />} onClick={() => setAddOpen(true)}>
            Add members
          </Button>
        )}
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={members.length === 0}
        emptyTitle="No team members yet"
        emptyText={canManage ? "Add people from your company to this project." : "No one is assigned yet."}
        onRetry={reload}
      >
        <div className={styles.grid}>
          {members.map((m) => (
            <div key={m.id} className={styles.card}>
              <span className={styles.avatar} aria-hidden="true">{initials(m.full_name, m.email)}</span>
              <div className={styles.info}>
                <span className={styles.name}>{m.full_name || m.email}</span>
                <span className={styles.email}>{m.email}</span>
                <div className={styles.roleRow}>
                  {m.role_names.length > 0 ? (
                    m.role_names.map((r) => <Badge key={r} tone="neutral">{r}</Badge>)
                  ) : (
                    <span className={styles.muted}>No role</span>
                  )}
                </div>
              </div>
              {canManage && (
                <div className={styles.cardActions}>
                  <button className={styles.accessBtn} title="Edit which parts of the project they can see"
                    onClick={() => setAccessFor(m)}>
                    Edit access
                  </button>
                  <button className={styles.remove} aria-label="Remove member" onClick={() => remove(m)}>
                    <Icon name="close" size={16} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </StateView>

      {addOpen && <AddTeamModal projectId={projectId} onClose={() => setAddOpen(false)} onAdded={reload} />}
      {accessFor && (
        <ScopeAccessModal projectId={projectId} memberId={accessFor.id}
          memberName={accessFor.full_name || accessFor.email}
          onClose={() => setAccessFor(null)} onSaved={reload} />
      )}
    </div>
  );
}

// --- Add members: pick users -> scope ---------------------------------------

function AddTeamModal({ projectId, onClose, onAdded }: { projectId: string; onClose: () => void; onAdded: () => void }) {
  const { data: users } = useFetch(
    () => api.get<{ id: string; email: string; full_name: string }[]>(`/projects/${projectId}/assignable-users/`),
    [projectId],
  );
  const [userIds, setUserIds] = useState<string[]>([]);
  const [scope, setScope] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = (users ?? []).map((u) => ({ value: u.id, label: u.full_name ? `${u.full_name} · ${u.email}` : u.email }));
  const toggleScope = (id: string) => setScope((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (userIds.length === 0) { setError("Pick at least one user."); return; }
    setBusy(true);
    setError(null);
    try {
      await api.post(`/projects/${projectId}/members/`, { user_ids: userIds, scope_ids: scope });
      onAdded();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add members.");
      setBusy(false);
    }
  }

  return (
    <Modal open title="Add team members" onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="add-team" disabled={busy}>{busy ? "Adding…" : "Add"}</Button>
        </>
      }>
      <form id="add-team" onSubmit={submit} className={styles.form}>
        <div className={styles.step}>
          <span className={styles.stepLabel}>1 · Users</span>
          <SearchSelect label="" placeholder="Search company users" options={options} value={userIds} onChange={setUserIds} multiple />
          <p className="formHint">
            Which modules they can open comes from their company role (Settings → Permissions) —
            shown next to their name below once added.
          </p>
        </div>

        <div className={styles.step}>
          <span className={styles.stepLabel}>2 · Scope (optional)</span>
          <p className="formHint">Tick the parts of the project they can see. Leave empty for the whole project.</p>
          <ScopeTree projectId={projectId} selectedIds={scope} onToggle={toggleScope} canManage />
        </div>

        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
