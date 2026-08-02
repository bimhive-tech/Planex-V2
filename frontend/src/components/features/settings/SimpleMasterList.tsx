"use client";

// One row-per-name CRUD list shared by Project Types and Priorities (Settings
// -> Master Data). Which endpoint/copy to use is passed in via `resource`.
import { useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { SimpleMasterFormModal } from "./SimpleMasterFormModal";
import { companyQuery } from "./companyQuery";
import styles from "./settingsList.module.css";

const COLS = { "--cols": "1fr auto" } as CSSProperties;

interface Row {
  id: string;
  name: string;
}

interface Props {
  resource: "project-types" | "project-priorities";
  label: string; // singular, e.g. "project type"
  labelPlural: string; // e.g. "project types"
  companyId: string;
}

export function SimpleMasterList({ resource, label, labelPlural, companyId }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<Row>>(`/${resource}/${companyQuery(companyId, { page_size: "200" })}`),
    [resource, companyId],
  );
  const rows = data?.results ?? [];

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }
  function openEdit(row: Row) {
    setEditing(row);
    setModalOpen(true);
  }

  async function handleDelete(row: Row) {
    if (!window.confirm(`Delete “${row.name}”? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/${resource}/${row.id}/${companyQuery(companyId)}`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : `Couldn't delete this ${label}.`);
    }
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>
          {data ? `${data.count} ${data.count === 1 ? label : labelPlural}` : labelPlural}
        </span>
        <Button size="sm" leadingIcon={<Icon name="plus" size={16} />} onClick={openCreate}>
          New {label}
        </Button>
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <div className={styles.surface} style={COLS}>
        <div className={styles.headRow}>
          <span>Name</span>
          <span />
        </div>

        <StateView
          loading={loading}
          error={error}
          isEmpty={rows.length === 0}
          emptyTitle={`No ${labelPlural} yet`}
          emptyText={`Add a ${label} so it shows up in the project form's dropdown.`}
          onRetry={reload}
        >
          {rows.map((r) => (
            <div key={r.id} className={styles.row}>
              <div className={styles.primary}>{r.name}</div>
              <div className={styles.actions}>
                <button className={styles.actionBtn} aria-label={`Rename ${r.name}`} onClick={() => openEdit(r)}>
                  <Icon name="edit" size={16} />
                </button>
                <button
                  className={`${styles.actionBtn} ${styles.danger}`}
                  aria-label={`Delete ${r.name}`}
                  onClick={() => handleDelete(r)}
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
        </StateView>
      </div>

      <SimpleMasterFormModal
        open={modalOpen}
        resource={resource}
        label={label}
        companyId={companyId}
        item={editing}
        onClose={() => setModalOpen(false)}
        onSaved={reload}
      />
    </div>
  );
}
