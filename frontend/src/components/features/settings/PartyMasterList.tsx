"use client";

// Consultants and contractors (Settings -> Master Data). Same shape as
// SimpleMasterList, plus the phone/email that make these worth storing once:
// picking one in the project form fills its contact details in too.
import { useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { PartyFormModal, type PartyRow } from "./PartyFormModal";
import { companyQuery } from "./companyQuery";
import styles from "./settingsList.module.css";

const COLS = { "--cols": "2fr 1fr 2fr auto" } as CSSProperties;

interface Props {
  resource: "consultants" | "contractors";
  label: string; // singular, e.g. "consultant"
  labelPlural: string;
  companyId: string;
}

export function PartyMasterList({ resource, label, labelPlural, companyId }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<PartyRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<PartyRow>>(`/${resource}/${companyQuery(companyId, { page_size: "200" })}`),
    [resource, companyId],
  );
  const rows = data?.results ?? [];

  async function handleDelete(row: PartyRow) {
    if (!window.confirm(`Delete “${row.name}”? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/${resource}/${row.id}/${companyQuery(companyId)}`);
      reload();
    } catch (err) {
      // The backend refuses while any project still names this party, and
      // says how many — surfacing that verbatim is more use than "couldn't
      // delete", since the fix is to go change those projects.
      setActionError(err instanceof ApiError ? err.message : `Couldn't delete this ${label}.`);
    }
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>
          {data ? `${data.count} ${data.count === 1 ? label : labelPlural}` : labelPlural}
        </span>
        <Button
          size="sm"
          leadingIcon={<Icon name="plus" size={16} />}
          onClick={() => { setEditing(null); setModalOpen(true); }}
        >
          New {label}
        </Button>
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <div className={styles.surface} style={COLS}>
        <div className={styles.headRow}>
          <span>Name</span>
          <span>Phone</span>
          <span>Email</span>
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
              <span className={styles.muted}>{r.phone || "—"}</span>
              <span className={styles.muted}>{r.email || "—"}</span>
              <div className={styles.actions}>
                <button
                  className={styles.actionBtn}
                  aria-label={`Edit ${r.name}`}
                  onClick={() => { setEditing(r); setModalOpen(true); }}
                >
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

      <PartyFormModal
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
