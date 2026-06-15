"use client";

// Settings → Permissions: a matrix with permissions as rows and roles as columns.
// Toggling a checkbox saves that role's permission set immediately (optimistic).
// Locked roles (Company Admin) are read-only.
import { useEffect, useState, useCallback } from "react";

import { StateView } from "@/components/ui/StateView";
import { Badge } from "@/components/ui/Badge";
import { api, ApiError, type Paginated } from "@/lib/api";
import type { PermissionGroup, RoleRow } from "@/types/settings";
import { CompanySelector } from "./CompanySelector";
import { companyQuery } from "./companyQuery";
import listStyles from "./settingsList.module.css";
import styles from "./PermissionsMatrix.module.css";

interface Props {
  isPlatformAdmin: boolean;
  ownCompanyId: string;
}

export function PermissionsMatrix({ isPlatformAdmin, ownCompanyId }: Props) {
  const [companyId, setCompanyId] = useState(ownCompanyId);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [groups, setGroups] = useState<PermissionGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [roleData, cat] = await Promise.all([
        api.get<Paginated<RoleRow>>(`/roles/${companyQuery(companyId, { page_size: "100" })}`),
        api.get<{ groups: PermissionGroup[] }>(`/permissions/${companyQuery(companyId)}`),
      ]);
      setRoles(roleData.results);
      setGroups(cat.groups);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load permissions.");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(role: RoleRow, permKey: string) {
    if (role.is_locked) return;
    const has = role.permissions.includes(permKey);
    const next = has ? role.permissions.filter((p) => p !== permKey) : [...role.permissions, permKey];
    // Optimistic update.
    setRoles((rs) => rs.map((r) => (r.id === role.id ? { ...r, permissions: next } : r)));
    setSaveError(null);
    try {
      await api.patch(`/roles/${role.id}/${companyQuery(companyId)}`, { permissions: next });
    } catch (err) {
      // Revert on failure.
      setRoles((rs) => rs.map((r) => (r.id === role.id ? { ...r, permissions: role.permissions } : r)));
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save change.");
    }
  }

  const isEmpty = roles.length === 0 || groups.length === 0;

  return (
    <div>
      <div className={listStyles.toolbar}>
        <div className={listStyles.toolbarLeft}>
          {isPlatformAdmin && <CompanySelector value={companyId} onChange={setCompanyId} />}
          <span className={listStyles.muted}>Check a box to grant a permission to a role.</span>
        </div>
      </div>

      {saveError && <p className="formError">{saveError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={isEmpty}
        emptyTitle="Nothing to show"
        emptyText="Create a role first, then assign permissions here."
        onRetry={load}
      >
        <div className={styles.scroll}>
          <table className={styles.matrix}>
            <thead>
              <tr>
                <th className={styles.cornerCell}>Permission</th>
                {roles.map((r) => (
                  <th key={r.id} className={styles.roleHead}>
                    <span className={styles.roleName}>{r.name}</span>
                    {r.is_locked && <Badge tone="info">Locked</Badge>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <GroupRows key={group.group} group={group} roles={roles} onToggle={toggle} />
              ))}
            </tbody>
          </table>
        </div>
      </StateView>
    </div>
  );
}

function GroupRows({
  group,
  roles,
  onToggle,
}: {
  group: PermissionGroup;
  roles: RoleRow[];
  onToggle: (role: RoleRow, key: string) => void;
}) {
  return (
    <>
      <tr>
        <td className={styles.groupHeader} colSpan={roles.length + 1}>
          {group.group}
        </td>
      </tr>
      {group.permissions.map((p) => (
        <tr key={p.key} className={styles.permRow}>
          <td className={styles.permCell}>{p.label}</td>
          {roles.map((r) => (
            <td key={r.id} className={styles.checkCell}>
              <input
                type="checkbox"
                className={styles.check}
                checked={r.permissions.includes(p.key)}
                disabled={r.is_locked}
                onChange={() => onToggle(r, p.key)}
                aria-label={`${p.label} for ${r.name}`}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
