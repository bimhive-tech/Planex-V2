"use client";

// Settings → Users: list users in the (selected) company with search + paging,
// create/edit via modal.
import { useEffect, useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { RoleRow, UserRow } from "@/types/settings";
import { CompanySelector } from "./CompanySelector";
import { UserFormModal } from "./UserFormModal";
import { companyQuery } from "./companyQuery";
import styles from "./settingsList.module.css";

const COLS = { "--cols": "2fr 1.5fr 0.8fr auto" } as CSSProperties;

interface Props {
  isPlatformAdmin: boolean;
  ownCompanyId: string;
  ownUserId: string;
}

export function UsersTab({ isPlatformAdmin, ownCompanyId, ownUserId }: Props) {
  const [companyId, setCompanyId] = useState(ownCompanyId);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [roleFilter, setRoleFilter] = useState(""); // "" = all roles (default)
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Roles for the filter dropdown (scoped to the selected company).
  const { data: roleData } = useFetch(
    () => api.get<Paginated<RoleRow>>(`/roles/${companyQuery(companyId, { page_size: "100" })}`),
    [companyId],
  );
  const roleOptions = [
    { value: "", label: "All roles" },
    ...(roleData?.results ?? []).map((r) => ({ value: r.id, label: r.name })),
  ];

  // Debounce the search box (~300ms) so typing doesn't spam the API.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, loading, error, reload } = useFetch(
    () =>
      api.get<Paginated<UserRow>>(
        `/users/${companyQuery(companyId, { page: String(page), search: debounced, role: roleFilter })}`,
      ),
    [companyId, page, debounced, roleFilter],
  );
  const rows = data?.results ?? [];

  function changeCompany(id: string) {
    setCompanyId(id);
    setRoleFilter(""); // roles are company-specific
    setPage(1);
  }

  function changeRole(id: string) {
    setRoleFilter(id);
    setPage(1);
  }

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }
  function openEdit(user: UserRow) {
    setEditing(user);
    setModalOpen(true);
  }

  async function handleDelete(user: UserRow) {
    if (!window.confirm(`Delete ${user.full_name || user.email}? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/users/${user.id}/${companyQuery(companyId)}`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete user.");
    }
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          {isPlatformAdmin && <CompanySelector value={companyId} onChange={changeCompany} />}
          <input
            className={styles.search}
            type="search"
            placeholder="Search users…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search users"
          />
          <Select
            options={roleOptions}
            value={roleFilter}
            onChange={(e) => changeRole(e.target.value)}
            aria-label="Filter by role"
          />
        </div>
        <Button size="sm" leadingIcon={<Icon name="plus" size={16} />} onClick={openCreate}>
          New user
        </Button>
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <div className={styles.surface} style={COLS}>
        <div className={styles.headRow}>
          <span>User</span>
          <span>Roles</span>
          <span>Status</span>
          <span />
        </div>

        <StateView
          loading={loading}
          error={error}
          isEmpty={rows.length === 0}
          emptyTitle="No users found"
          emptyText={debounced ? "Try a different search." : "Create the first user for this company."}
          onRetry={reload}
        >
          {rows.map((u) => (
            <div key={u.id} className={styles.row}>
              <div>
                <div className={styles.primary}>{u.full_name}</div>
                <div className={styles.muted}>{u.email}</div>
              </div>
              <div className={styles.chips}>
                {u.roles.length ? (
                  u.roles.map((r) => <Badge key={r} tone="neutral">{r}</Badge>)
                ) : (
                  <span className={styles.muted}>—</span>
                )}
              </div>
              <span>
                <Badge tone={u.is_active ? "success" : "neutral"}>
                  {u.is_active ? "Active" : "Inactive"}
                </Badge>
              </span>
              <div className={styles.actions}>
                <button className={styles.actionBtn} aria-label="Edit user" onClick={() => openEdit(u)}>
                  <Icon name="edit" size={16} />
                </button>
                <button
                  className={`${styles.actionBtn} ${styles.danger}`}
                  aria-label="Delete user"
                  disabled={u.id === ownUserId}
                  onClick={() => handleDelete(u)}
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
        </StateView>

        {data && (data.next || data.previous) && (
          <div className={styles.footer}>
            <span>
              {data.count} {data.count === 1 ? "user" : "users"} · page {page}
            </span>
            <div className={styles.pageBtns}>
              <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      <UserFormModal
        open={modalOpen}
        contextCompanyId={companyId}
        isPlatformAdmin={isPlatformAdmin}
        user={editing}
        onClose={() => setModalOpen(false)}
        onSaved={reload}
      />
    </div>
  );
}
