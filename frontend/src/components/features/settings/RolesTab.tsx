"use client";

// Settings → Roles: list roles for the (selected) company, create/edit with
// permission checkboxes, delete when unused.
import { useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { RoleRow } from "@/types/settings";
import { CompanySelector } from "./CompanySelector";
import { RoleFormModal } from "./RoleFormModal";
import { companyQuery } from "./companyQuery";
import styles from "./settingsList.module.css";

const COLS = { "--cols": "2fr 1fr 1fr auto" } as CSSProperties;

interface Props {
  isPlatformAdmin: boolean;
  ownCompanyId: string;
}

export function RolesTab({ isPlatformAdmin, ownCompanyId }: Props) {
  const [companyId, setCompanyId] = useState(ownCompanyId);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RoleRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<RoleRow>>(`/roles/${companyQuery(companyId, { page_size: "100" })}`),
    [companyId],
  );
  const rows = data?.results ?? [];

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }
  function openEdit(role: RoleRow) {
    setEditing(role);
    setModalOpen(true);
  }

  async function handleDelete(role: RoleRow) {
    if (!window.confirm(`Delete the role “${role.name}”? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/roles/${role.id}/${companyQuery(companyId)}`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete role.");
    }
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          {isPlatformAdmin && <CompanySelector value={companyId} onChange={setCompanyId} />}
          <span className={styles.muted}>
            {data ? `${data.count} ${data.count === 1 ? "role" : "roles"}` : "Roles"}
          </span>
        </div>
        <Button size="sm" leadingIcon={<Icon name="plus" size={16} />} onClick={openCreate}>
          New role
        </Button>
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <div className={styles.surface} style={COLS}>
        <div className={styles.headRow}>
          <span>Role</span>
          <span>Permissions</span>
          <span>Members</span>
          <span />
        </div>

        <StateView
          loading={loading}
          error={error}
          isEmpty={rows.length === 0}
          emptyTitle="No roles yet"
          emptyText="Create a role and choose its permissions."
          onRetry={reload}
        >
          {rows.map((r) => (
            <div key={r.id} className={styles.row}>
              <div>
                <div className={styles.primary}>{r.name}</div>
                {r.is_platform_role && <div className={styles.muted}>System role</div>}
              </div>
              <span>
                <Badge tone="neutral">
                  {r.permissions.length} {r.permissions.length === 1 ? "permission" : "permissions"}
                </Badge>
              </span>
              <span className="tnum">{r.member_count}</span>
              <div className={styles.actions}>
                <button className={styles.actionBtn} aria-label="Edit role" onClick={() => openEdit(r)}>
                  <Icon name="edit" size={16} />
                </button>
                <button
                  className={`${styles.actionBtn} ${styles.danger}`}
                  aria-label="Delete role"
                  onClick={() => handleDelete(r)}
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
        </StateView>
      </div>

      <RoleFormModal
        open={modalOpen}
        companyId={companyId}
        role={editing}
        onClose={() => setModalOpen(false)}
        onSaved={reload}
      />
    </div>
  );
}
