"use client";

// Settings -> Master Data -> Currencies: create/edit/delete + choose which one
// is the default (the one new projects start with).
import { useState, type CSSProperties } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { CurrencyRow } from "@/types/settings";
import { CurrencyFormModal } from "./CurrencyFormModal";
import { companyQuery } from "./companyQuery";
import styles from "./settingsList.module.css";

const COLS = { "--cols": "1fr 2fr 1fr 1fr auto" } as CSSProperties;

export function CurrencyList({ companyId }: { companyId: string }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CurrencyRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<CurrencyRow>>(`/currencies/${companyQuery(companyId, { page_size: "200" })}`),
    [companyId],
  );
  const rows = data?.results ?? [];

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }
  function openEdit(currency: CurrencyRow) {
    setEditing(currency);
    setModalOpen(true);
  }

  async function handleSetDefault(currency: CurrencyRow) {
    setActionError(null);
    try {
      await api.post(`/currencies/${currency.id}/set-default/${companyQuery(companyId)}`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't set the default currency.");
    }
  }

  async function handleDelete(currency: CurrencyRow) {
    if (!window.confirm(`Delete “${currency.code}”? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/currencies/${currency.id}/${companyQuery(companyId)}`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete this currency.");
    }
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>
          {data ? `${data.count} ${data.count === 1 ? "currency" : "currencies"}` : "Currencies"}
        </span>
        <Button size="sm" leadingIcon={<Icon name="plus" size={16} />} onClick={openCreate}>
          New currency
        </Button>
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <div className={styles.surface} style={COLS}>
        <div className={styles.headRow}>
          <span>Code</span>
          <span>Name</span>
          <span>Symbol</span>
          <span>Default</span>
          <span />
        </div>

        <StateView
          loading={loading}
          error={error}
          isEmpty={rows.length === 0}
          emptyTitle="No currencies yet"
          emptyText="Add a currency so it shows up in the project form's dropdown."
          onRetry={reload}
        >
          {rows.map((c) => (
            <div key={c.id} className={styles.row}>
              <div className={styles.primary}>{c.code}</div>
              <span>{c.name}</span>
              <span className={styles.muted}>{c.symbol || "—"}</span>
              <span>
                {c.is_default ? (
                  <Badge tone="info">Default</Badge>
                ) : (
                  <button className={styles.actionBtn} onClick={() => handleSetDefault(c)}>
                    Set default
                  </button>
                )}
              </span>
              <div className={styles.actions}>
                <button className={styles.actionBtn} aria-label={`Edit ${c.code}`} onClick={() => openEdit(c)}>
                  <Icon name="edit" size={16} />
                </button>
                <button
                  className={`${styles.actionBtn} ${styles.danger}`}
                  aria-label={`Delete ${c.code}`}
                  disabled={c.is_default}
                  onClick={() => handleDelete(c)}
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
        </StateView>
      </div>

      <CurrencyFormModal
        open={modalOpen}
        companyId={companyId}
        currency={editing}
        onClose={() => setModalOpen(false)}
        onSaved={reload}
      />
    </div>
  );
}
