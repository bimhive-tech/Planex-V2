"use client";

// Settings → Companies (platform admin): list companies, create new shells.
import { useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { TypedConfirmModal } from "@/components/ui/ConfirmModal";
import { api, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import type { CompanyRow } from "@/types/settings";
import { CompanyFormModal } from "./CompanyFormModal";
import styles from "./settingsList.module.css";

const COLS = { "--cols": "2fr 1fr 1fr 1fr auto" } as CSSProperties;

export function CompaniesTab() {
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [deleting, setDeleting] = useState<CompanyRow | null>(null);
  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<CompanyRow>>(`/companies/?page=${page}`),
    [page],
  );

  const rows = data?.results ?? [];

  async function confirmDelete() {
    if (!deleting) return;
    await api.del(`/companies/${deleting.id}/`);
    reload();
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>
          {data ? `${data.count} ${data.count === 1 ? "company" : "companies"}` : "Companies"}
        </span>
        <Button size="sm" leadingIcon={<Icon name="plus" size={16} />} onClick={() => setModalOpen(true)}>
          New company
        </Button>
      </div>

      <div className={styles.surface} style={COLS}>
        <div className={styles.headRow}>
          <span>Name</span>
          <span>Users</span>
          <span>Status</span>
          <span>Created</span>
          <span />
        </div>

        <StateView
          loading={loading}
          error={error}
          isEmpty={rows.length === 0}
          emptyTitle="No companies yet"
          emptyText="Create your first company to get started."
          onRetry={reload}
        >
          {rows.map((c) => (
            <div key={c.id} className={styles.row}>
              <div>
                <div className={styles.primary}>{c.name}</div>
                <div className={styles.muted}>{c.slug}</div>
              </div>
              <span className="tnum">{c.user_count}</span>
              <span>
                {c.is_platform_admin ? (
                  <Badge tone="info">Platform</Badge>
                ) : (
                  <Badge tone={c.is_active ? "success" : "neutral"}>
                    {c.is_active ? "Active" : "Inactive"}
                  </Badge>
                )}
              </span>
              <span className={styles.muted}>{formatDate(c.created_at)}</span>
              <div className={styles.actions}>
                <button
                  className={`${styles.actionBtn} ${styles.danger}`}
                  aria-label="Delete company"
                  disabled={c.is_platform_admin}
                  onClick={() => setDeleting(c)}
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
        </StateView>

        {data && (data.next || data.previous) && (
          <div className={styles.footer}>
            <span>Page {page}</span>
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

      <CompanyFormModal open={modalOpen} onClose={() => setModalOpen(false)} onCreated={reload} />

      <TypedConfirmModal
        open={!!deleting}
        title="Delete company"
        confirmPhrase={deleting?.name ?? ""}
        confirmLabel="Delete company"
        description={
          <>
            This permanently deletes <strong>{deleting?.name}</strong> and all of its users,
            roles, and data. This cannot be undone.
          </>
        }
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
