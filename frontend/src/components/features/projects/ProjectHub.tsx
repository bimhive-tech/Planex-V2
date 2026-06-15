"use client";

// Project Hub: search/filter, a responsive grid of project cards, and the
// create/edit drawer. Handles archive + delete inline.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { PROJECT_TYPES } from "@/lib/projectTypes";
import type { ProjectListRow } from "@/types/project";
import { ProjectCard } from "./ProjectCard";
import { ProjectFormDrawer } from "./ProjectFormDrawer";
import styles from "./projectHub.module.css";

const TYPE_OPTIONS = [{ value: "", label: "All types" }, ...PROJECT_TYPES];
const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];

export function ProjectHub({ canManage }: { canManage: boolean }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(1);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = new URLSearchParams({ page: String(page), status });
  if (debounced) query.set("search", debounced);
  if (type) query.set("type", type);

  const { data, loading, error, reload } = useFetch(
    () => api.get<Paginated<ProjectListRow>>(`/projects/?${query.toString()}`),
    [debounced, type, status, page],
  );
  const rows = data?.results ?? [];

  function openCreate() {
    setEditId(null);
    setDrawerOpen(true);
  }
  function openEdit(id: string) {
    setEditId(id);
    setDrawerOpen(true);
  }

  async function handleArchive(p: ProjectListRow) {
    setActionError(null);
    try {
      await api.patch(`/projects/${p.id}/`, { is_archived: !p.is_archived });
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update project.");
    }
  }

  async function handleDelete(p: ProjectListRow) {
    if (!window.confirm(`Delete “${p.name}”? This can't be undone.`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${p.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete project.");
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>Projects</h1>
          <p className={styles.subtitle}>
            {data ? `${data.count} ${data.count === 1 ? "project" : "projects"}` : "Your company’s projects"}
          </p>
        </div>
        {canManage && (
          <Button leadingIcon={<Icon name="plus" size={16} />} onClick={openCreate}>
            New project
          </Button>
        )}
      </header>

      <div className={styles.filters}>
        <input
          className={styles.search}
          type="search"
          placeholder="Search projects…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search projects"
        />
        <Select options={TYPE_OPTIONS} value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Filter by type" />
        <Select options={STATUS_OPTIONS} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Filter by status" />
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={rows.length === 0}
        emptyTitle="No projects found"
        emptyText={canManage ? "Create your first project to get started." : "Nothing to show here yet."}
        onRetry={reload}
      >
        <div className={styles.grid}>
          {rows.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              canManage={canManage}
              onEdit={openEdit}
              onArchive={handleArchive}
              onDelete={handleDelete}
            />
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

      <ProjectFormDrawer
        open={drawerOpen}
        projectId={editId}
        onClose={() => setDrawerOpen(false)}
        onSaved={reload}
      />
    </div>
  );
}
