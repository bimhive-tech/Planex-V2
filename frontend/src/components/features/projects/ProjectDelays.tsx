"use client";

// Project Delays / Obstacles tab — the «المعوقات» data, pulled into the report.
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

interface Delay {
  id: string;
  title: string;
  description: string;
  impact_days: number;
  status: string;
  status_display: string;
  date: string | null;
}

const STATUSES = [
  { value: "open", label: "Open" },
  { value: "resolved", label: "Resolved" },
];

export function ProjectDelays({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Delay[]>(`/projects/${projectId}/delays/`),
    [projectId],
  );
  const [modal, setModal] = useState<{ delay: Delay | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];

  async function remove(d: Delay) {
    if (!window.confirm(`Delete “${d.title}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/delays/${d.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Obstacles &amp; Delays</h2>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />}
            onClick={() => setModal({ delay: null })}>
            Add
          </Button>
        )}
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={items.length === 0}
        emptyTitle="No delays logged"
        emptyText={canManage ? "Log obstacles and their day impact — they appear in the report." : undefined}
        onRetry={reload}
      >
        <ul className={styles.list}>
          {items.map((d) => (
            <li key={d.id} className={styles.item}>
              <span className={`${styles.dot} ${styles[`s_${d.status === "resolved" ? "completed" : "in_progress"}`]}`} aria-hidden="true" />
              <div className={styles.itemBody}>
                <span className={styles.itemTitle}>{d.title}</span>
                <span className={styles.itemMeta}>
                  {d.status_display} · {d.impact_days} day{d.impact_days === 1 ? "" : "s"}
                  {d.date ? ` · ${formatDate(d.date)}` : ""}
                </span>
              </div>
              {canManage && (
                <div className={styles.itemActions}>
                  <button className={styles.iconBtn} aria-label="Edit" onClick={() => setModal({ delay: d })}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button className={styles.iconBtn} aria-label="Delete" onClick={() => remove(d)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </StateView>

      {modal && (
        <DelayModal projectId={projectId} delay={modal.delay}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}

function DelayModal({ projectId, delay, onClose, onSaved }: {
  projectId: string; delay: Delay | null; onClose: () => void; onSaved: () => void;
}) {
  const isEdit = !!delay;
  const [title, setTitle] = useState("");
  const [impact, setImpact] = useState("0");
  const [statusV, setStatusV] = useState("open");
  const [date, setDate] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(delay?.title ?? "");
    setImpact(String(delay?.impact_days ?? 0));
    setStatusV(delay?.status ?? "open");
    setDate(delay?.date ?? "");
    setDescription(delay?.description ?? "");
  }, [delay]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const body = { title, impact_days: Number(impact) || 0, status: statusV, date: date || null, description };
    try {
      if (isEdit && delay) await api.patch(`/projects/${projectId}/delays/${delay.id}/`, body);
      else await api.post(`/projects/${projectId}/delays/`, body);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <Modal open title={isEdit ? "Edit delay" : "Add delay"} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="delay-form" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
        </>
      }>
      <form id="delay-form" onSubmit={submit} className={styles.form}>
        <Input label="Obstacle / delay" name="title" required autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input label="Impact (days)" name="impact" type="number" min="0" value={impact} onChange={(e) => setImpact(e.target.value)} />
        <Select label="Status" options={STATUSES} value={statusV} onChange={(e) => setStatusV(e.target.value)} />
        <Input label="Date" name="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
