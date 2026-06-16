"use client";

// Team tab: member cards (avatar, name, role, email) + add/remove. Mirrors the
// reference "Project Team" panel.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { SearchSelect } from "@/components/ui/SearchSelect";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
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
            Add member
          </Button>
        )}
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={members.length === 0}
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
                  <button className={styles.accessBtn} title="Manage zone access" onClick={() => setAccessFor(m)}>
                    Access
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

      {addOpen && (
        <AddMemberModal projectId={projectId} onClose={() => setAddOpen(false)} onAdded={reload} />
      )}
      {accessFor && (
        <ScopeAccessModal
          projectId={projectId} memberId={accessFor.id} memberName={accessFor.full_name || accessFor.email}
          onClose={() => setAccessFor(null)} onSaved={reload}
        />
      )}
    </div>
  );
}

function AddMemberModal({ projectId, onClose, onAdded }: { projectId: string; onClose: () => void; onAdded: () => void }) {
  const { data } = useFetch(
    () => api.get<{ id: string; email: string; full_name: string }[]>(`/projects/${projectId}/assignable-users/`),
    [projectId],
  );
  const [userId, setUserId] = useState<string[]>([]);
  const [role, setRole] = useState("member");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = (data ?? []).map((u) => ({ value: u.id, label: u.full_name ? `${u.full_name} · ${u.email}` : u.email }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!userId[0]) { setError("Pick a user."); return; }
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/projects/${projectId}/members/`, { user_id: userId[0], role });
      onAdded();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add member.");
      setSubmitting(false);
    }
  }

  return (
    <Modal open title="Add team member" onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="add-member" disabled={submitting}>{submitting ? "Adding…" : "Add"}</Button>
        </>
      }>
      <form id="add-member" onSubmit={submit} className={styles.form}>
        <SearchSelect label="User" placeholder="Search company users" options={options} value={userId} onChange={setUserId} />
        <Select label="Role" options={[...PROJECT_ROLES]} value={role} onChange={(e) => setRole(e.target.value)} />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
