"use client";

// Team tab: member cards (avatar, name, role, email) + add/remove/scope. Module
// access (which tabs a member sees) comes from their COMPANY role — configured
// in Settings → Permissions — not from this screen. What IS project-specific is
// scope: which parts of the project a member can see within the modules their
// role already grants them.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { SearchSelect } from "@/components/ui/SearchSelect";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { ScopeTree } from "@/components/features/reports/ScopeTree";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { PROJECT_ROLES, type ProjectMember } from "@/types/project";
import { ScopeAccessModal } from "./ScopeAccessModal";
import styles from "./projectTeam.module.css";

const ROLE_TONE: Record<string, "info" | "success" | "warning" | "neutral"> = {
  manager: "info", reviewer: "warning", engineer: "success", member: "neutral",
};

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

  async function changeRole(m: ProjectMember, role: string) {
    setActionError(null);
    try {
      await api.patch(`/projects/${projectId}/members/${m.id}/`, { role });
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update role.");
    }
  }

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
                  {canManage ? (
                    <Select className={styles.roleSelect} options={[...PROJECT_ROLES]} value={m.role}
                      onChange={(e) => changeRole(m, e.target.value)} aria-label="Role" />
                  ) : (
                    <Badge tone={ROLE_TONE[m.role] ?? "neutral"}>{m.role_display}</Badge>
                  )}
                </div>
              </div>
              {canManage && (
                <div className={styles.cardActions}>
                  <button className={styles.accessBtn} title="Manage scope" onClick={() => setAccessFor(m)}>
                    Scope
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

// --- Add members: pick users -> role -> scope -------------------------------

function AddTeamModal({ projectId, onClose, onAdded }: { projectId: string; onClose: () => void; onAdded: () => void }) {
  const { data: users } = useFetch(
    () => api.get<{ id: string; email: string; full_name: string }[]>(`/projects/${projectId}/assignable-users/`),
    [projectId],
  );
  const [userIds, setUserIds] = useState<string[]>([]);
  const [role, setRole] = useState("member");
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
      await api.post(`/projects/${projectId}/members/`, { user_ids: userIds, role, scope_ids: scope });
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
          <Select label="Project role" options={[...PROJECT_ROLES]} value={role} onChange={(e) => setRole(e.target.value)} />
          <p className="formHint">
            Which modules they can access comes from their company role (Settings → Permissions), not this form.
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
