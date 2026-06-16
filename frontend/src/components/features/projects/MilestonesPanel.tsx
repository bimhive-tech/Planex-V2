"use client";

// Key Milestones card (Overview): timeline of project milestones with status,
// plus add/edit/delete for managers. Mirrors the reference panel.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import styles from "./milestones.module.css";

interface Milestone {
  id: string;
  title: string;
  date: string | null;
  status: string;
  status_display: string;
  sort_order: number;
}

const STATUSES = [
  { value: "completed", label: "Completed" },
  { value: "in_progress", label: "In Progress" },
  { value: "upcoming", label: "Upcoming" },
];

export function MilestonesPanel({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Milestone[]>(`/projects/${projectId}/milestones/`),
    [projectId],
  );
  const [modal, setModal] = useState<{ milestone: Milestone | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];

  async function remove(m: Milestone) {
    if (!window.confirm(`Delete milestone “${m.title}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/milestones/${m.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={`${styles.card}`}>
      <header className={styles.head}>
        <h2 className={styles.title}>Key Milestones</h2>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />}
            onClick={() => setModal({ milestone: null })}>
            Add
          </Button>
        )}
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={items.length === 0}
        emptyTitle="No milestones yet"
        emptyText={canManage ? "Add key dates like kickoff, design approval, handover." : undefined}
        onRetry={reload}
      >
        <ul className={styles.list}>
          {items.map((m) => (
            <li key={m.id} className={styles.item}>
              <span className={`${styles.dot} ${styles[`s_${m.status}`]}`} aria-hidden="true">
                {m.status === "completed" && <Icon name="check" size={12} />}
              </span>
              <div className={styles.itemBody}>
                <span className={styles.itemTitle}>{m.title}</span>
                <span className={styles.itemMeta}>
                  {m.status_display}{m.date ? ` · ${formatDate(m.date)}` : ""}
                </span>
              </div>
              {canManage && (
                <div className={styles.itemActions}>
                  <button className={styles.iconBtn} aria-label="Edit" onClick={() => setModal({ milestone: m })}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button className={styles.iconBtn} aria-label="Delete" onClick={() => remove(m)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </StateView>

      {modal && (
        <MilestoneModal projectId={projectId} milestone={modal.milestone}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}

function MilestoneModal({ projectId, milestone, onClose, onSaved }: {
  projectId: string; milestone: Milestone | null; onClose: () => void; onSaved: () => void;
}) {
  const isEdit = !!milestone;
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [statusV, setStatusV] = useState("upcoming");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(milestone?.title ?? "");
    setDate(milestone?.date ?? "");
    setStatusV(milestone?.status ?? "upcoming");
  }, [milestone]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const body = { title, date: date || null, status: statusV };
    try {
      if (isEdit && milestone) {
        await api.patch(`/projects/${projectId}/milestones/${milestone.id}/`, body);
      } else {
        await api.post(`/projects/${projectId}/milestones/`, body);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save milestone.");
      setSubmitting(false);
    }
  }

  return (
    <Modal open title={isEdit ? "Edit milestone" : "Add milestone"} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="milestone-form" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
        </>
      }>
      <form id="milestone-form" onSubmit={submit} className={styles.form}>
        <Input label="Title" name="title" required autoFocus placeholder="e.g. Design Approval"
          value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input label="Date" name="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <Select label="Status" options={STATUSES} value={statusV} onChange={(e) => setStatusV(e.target.value)} />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
