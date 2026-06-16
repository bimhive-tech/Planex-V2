"use client";

// Templates Hub: the library of report designs. Create a template (name only —
// it starts from sensible defaults) then open the builder to control everything.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import type { ReportTemplate } from "@/types/report";
import styles from "./reports.module.css";

function fmt(date: string): string {
  return new Date(date).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export function TemplatesHub() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<ReportTemplate>>(`/report-templates/?page=${page}`),
    [page],
  );
  const rows = data?.results ?? [];

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setActionError(null);
    try {
      const created = await api.post<ReportTemplate>("/report-templates/", { name });
      router.push(`${ROUTES.reportTemplates}/${created.id}`);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't create template.");
      setSaving(false);
    }
  }

  async function handleDelete(t: ReportTemplate) {
    if (!window.confirm(`Delete “${t.name}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/report-templates/${t.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete template.");
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.headRow}>
          <div>
            <h1 className={styles.title}>Report templates</h1>
            <p className={styles.subtitle}>Design how reports look — cover, fonts, colors, sections, and labels.</p>
          </div>
          <Button leadingIcon={<Icon name="plus" size={16} />} onClick={() => { setName(""); setCreateOpen(true); }}>
            New template
          </Button>
        </div>
        <nav className={styles.tabs}>
          <Link href={ROUTES.reports} className={styles.tab}>Reports</Link>
          <span className={`${styles.tab} ${styles.tabActive}`}>Templates</span>
        </nav>
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={rows.length === 0}
        emptyTitle="No templates yet"
        emptyText="Create a template to control every part of your reports."
        onRetry={reload}
      >
        <div className={styles.grid}>
          {rows.map((t) => (
            <article key={t.id} className={styles.card}>
              <div className={styles.cardTop}>
                <h3 className={styles.cardTitle}>{t.name}</h3>
                {t.is_default && <Badge tone="info">Default</Badge>}
              </div>
              <div className={styles.cardMeta}>
                <span className={styles.metaItem}><Icon name="clock" size={14} />Updated {fmt(t.updated_at)}</span>
              </div>
              <div className={styles.cardActions}>
                <Link className={styles.iconBtn} href={`${ROUTES.reportTemplates}/${t.id}`} aria-label="Edit design" title="Edit design">
                  <Icon name="edit" size={16} />
                </Link>
                <button className={`${styles.iconBtn} ${styles.danger}`} onClick={() => handleDelete(t)} aria-label="Delete" title="Delete">
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </article>
          ))}
        </div>
      </StateView>

      {data && (data.next || data.previous) && (
        <div className={styles.pagination}>
          <span>Page {page}</span>
          <div className={styles.pageBtns}>
            <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      <Drawer
        open={createOpen}
        title="New template"
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="secondary" type="button" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button type="submit" form="template-create" disabled={saving || !name.trim()}>
              {saving ? "Creating…" : "Create & design"}
            </Button>
          </>
        }
      >
        <form id="template-create" onSubmit={handleCreate} className={styles.drawerForm}>
          <Input label="Template name" name="name" required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </form>
      </Drawer>
    </div>
  );
}
