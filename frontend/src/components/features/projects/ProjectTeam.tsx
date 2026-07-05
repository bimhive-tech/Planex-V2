"use client";

// Team tab: member cards with per-project module permissions + scope. Managers
// add people (pick users -> tick modules -> tick scope) and edit each member's
// permissions/scope later. Least privilege: a member only sees ticked modules.
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { SearchSelect } from "@/components/ui/SearchSelect";
import { Checkbox } from "@/components/ui/Checkbox";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { ScopeTree } from "@/components/features/reports/ScopeTree";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { PROJECT_ROLES, type ProjectMember, type ProjectPermGroup } from "@/types/project";
import { ScopeAccessModal } from "./ScopeAccessModal";
import styles from "./projectTeam.module.css";

function initials(name: string, email: string) {
  const base = name.trim() || email;
  const parts = base.split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || email[0].toUpperCase();
}

/** The project-permission catalog (fetched once) — powers every checkbox matrix. */
function usePermCatalog() {
  return useFetch(() => api.get<ProjectPermGroup[]>("/project-permissions/catalog/"), []);
}

/** Checkbox grid of module permissions, grouped. */
function PermissionMatrix({ catalog, selected, onToggle }: {
  catalog: ProjectPermGroup[]; selected: Set<string>; onToggle: (key: string) => void;
}) {
  return (
    <div className={styles.matrix}>
      {catalog.map((g) => (
        <div key={g.group} className={styles.matrixGroup}>
          <span className={styles.matrixLabel}>{g.group}</span>
          <div className={styles.matrixItems}>
            {g.permissions.map((p) => (
              <Checkbox key={p.key} name={`perm-${p.key}`} label={p.label}
                checked={selected.has(p.key)} onChange={() => onToggle(p.key)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ProjectTeam({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ProjectMember[]>(`/projects/${projectId}/members/`),
    [projectId],
  );
  const [addOpen, setAddOpen] = useState(false);
  const [permsFor, setPermsFor] = useState<ProjectMember | null>(null);
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
        emptyText={canManage ? "Add people and choose which modules they can access." : "No one is assigned yet."}
        onRetry={reload}
      >
        <div className={styles.grid}>
          {members.map((m) => (
            <div key={m.id} className={styles.card}>
              <span className={styles.avatar} aria-hidden="true">{initials(m.full_name, m.email)}</span>
              <div className={styles.info}>
                <span className={styles.name}>{m.full_name || m.email}</span>
                <span className={styles.email}>{m.email}</span>
                <span className={styles.permCount}>
                  {m.permissions.length} module{m.permissions.length === 1 ? "" : "s"}
                </span>
              </div>
              {canManage && (
                <div className={styles.cardActions}>
                  <button className={styles.accessBtn} onClick={() => setPermsFor(m)}>Permissions</button>
                  <button className={styles.accessBtn} onClick={() => setAccessFor(m)}>Scope</button>
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
      {permsFor && (
        <MemberPermissionsModal projectId={projectId} member={permsFor}
          onClose={() => setPermsFor(null)} onSaved={reload} />
      )}
      {accessFor && (
        <ScopeAccessModal projectId={projectId} memberId={accessFor.id}
          memberName={accessFor.full_name || accessFor.email}
          onClose={() => setAccessFor(null)} onSaved={reload} />
      )}
    </div>
  );
}

// --- Add members: pick users -> tick modules -> tick scope -----------------

function AddTeamModal({ projectId, onClose, onAdded }: { projectId: string; onClose: () => void; onAdded: () => void }) {
  const { data: users } = useFetch(
    () => api.get<{ id: string; email: string; full_name: string }[]>(`/projects/${projectId}/assignable-users/`),
    [projectId],
  );
  const { data: catalog } = usePermCatalog();
  const [userIds, setUserIds] = useState<string[]>([]);
  const [role, setRole] = useState("member");
  const [perms, setPerms] = useState<Set<string>>(new Set(["overview", "schedule"]));
  const [scope, setScope] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = (users ?? []).map((u) => ({ value: u.id, label: u.full_name ? `${u.full_name} · ${u.email}` : u.email }));
  const togglePerm = (k: string) => setPerms((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleScope = (id: string) => setScope((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (userIds.length === 0) { setError("Pick at least one user."); return; }
    setBusy(true);
    setError(null);
    try {
      await api.post(`/projects/${projectId}/members/`, {
        user_ids: userIds, role, permissions: [...perms], scope_ids: scope,
      });
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
        </div>

        <div className={styles.step}>
          <span className={styles.stepLabel}>2 · Module permissions</span>
          {catalog ? <PermissionMatrix catalog={catalog} selected={perms} onToggle={togglePerm} />
                   : <p className="formHint">Loading…</p>}
        </div>

        <div className={styles.step}>
          <span className={styles.stepLabel}>3 · Scope (optional)</span>
          <p className="formHint">Tick the parts of the project they can see. Leave empty for the whole project.</p>
          <ScopeTree projectId={projectId} selectedIds={scope} onToggle={toggleScope} canManage />
        </div>

        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}

// --- Edit a member's module permissions ------------------------------------

function MemberPermissionsModal({ projectId, member, onClose, onSaved }: {
  projectId: string; member: ProjectMember; onClose: () => void; onSaved: () => void;
}) {
  const { data: catalog } = usePermCatalog();
  const [perms, setPerms] = useState<Set<string>>(new Set(member.permissions));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (k: string) => setPerms((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/projects/${projectId}/members/${member.id}/`, { permissions: [...perms] });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save permissions.");
      setBusy(false);
    }
  }

  return (
    <Modal open title={`Permissions · ${member.full_name || member.email}`} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="button" onClick={save} disabled={busy || !catalog}>{busy ? "Saving…" : "Save"}</Button>
        </>
      }>
      <div className={styles.form}>
        {catalog ? <PermissionMatrix catalog={catalog} selected={perms} onToggle={toggle} />
                 : <p className="formHint">Loading…</p>}
        {error && <p className="formError">{error}</p>}
      </div>
    </Modal>
  );
}
