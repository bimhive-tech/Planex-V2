"use client";

// Submittals tab — shop drawings & material submittals and their approval
// status (the report's «موقف الرسومات / موقف اعتماد المواد» section).
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { API_BASE } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import styles from "./finances.module.css";

interface Submittal {
  id: string; title: string;
  submittal_type: string; type_display: string;
  discipline: string; discipline_display: string;
  status: string; status_display: string;
  reference: string; date: string | null; has_attachment: boolean;
}

const TYPES = [
  { value: "shop_drawing", label: "Shop Drawing" },
  { value: "material", label: "Material" },
];
const DISCIPLINES = [
  { value: "concrete", label: "Concrete" },
  { value: "architecture", label: "Architecture" },
  { value: "electrical", label: "Electrical" },
  { value: "mechanical", label: "Mechanical" },
  { value: "other", label: "Other" },
];
const STATUSES = [
  { value: "pending", label: "Pending" },
  { value: "under_review", label: "Under Review" },
  { value: "approved", label: "Approved" },
  { value: "approved_with_comments", label: "Approved with comments" },
  { value: "rejected", label: "Rejected" },
];

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  approved: "success", approved_with_comments: "success",
  pending: "neutral", under_review: "info", rejected: "danger",
};

export function ProjectSubmittals({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Submittal[]>(`/projects/${projectId}/submittals/`),
    [projectId],
  );
  const [modal, setModal] = useState<{ submittal: Submittal | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];

  async function remove(s: Submittal) {
    if (!window.confirm(`Delete “${s.title}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/submittals/${s.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Submittals</h2>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />} onClick={() => setModal({ submittal: null })}>
            Add
          </Button>
        )}
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={items.length === 0}
        emptyTitle="No submittals yet"
        emptyText={canManage ? "Track shop drawings & material submittals and their approval status." : undefined}
        onRetry={reload}
      >
        <ul className={styles.list}>
          {items.map((s) => (
            <li key={s.id} className={styles.item}>
              <div className={styles.itemBody}>
                <span className={styles.itemTitle}>{s.title}</span>
                <span className={styles.muted}>
                  {s.type_display} · {s.discipline_display}
                  {s.reference ? ` · ${s.reference}` : ""}
                  {s.date ? ` · ${formatDate(s.date)}` : ""}
                  {s.has_attachment && (
                    <>
                      {" · "}
                      <a className={styles.link} href={`${API_BASE}/projects/${projectId}/submittals/${s.id}/file/`} target="_blank" rel="noreferrer">
                        Attachment
                      </a>
                    </>
                  )}
                </span>
              </div>
              <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status_display}</Badge>
              {canManage && (
                <div className={styles.itemActions}>
                  <button className={styles.iconBtn} aria-label="Edit" onClick={() => setModal({ submittal: s })}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button className={styles.iconBtn} aria-label="Delete" onClick={() => remove(s)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </StateView>

      {modal && (
        <SubmittalModal projectId={projectId} submittal={modal.submittal}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}

function SubmittalModal({ projectId, submittal, onClose, onSaved }: {
  projectId: string; submittal: Submittal | null; onClose: () => void; onSaved: () => void;
}) {
  const isEdit = !!submittal;
  const [title, setTitle] = useState("");
  const [type, setType] = useState("shop_drawing");
  const [discipline, setDiscipline] = useState("other");
  const [statusV, setStatusV] = useState("pending");
  const [reference, setReference] = useState("");
  const [date, setDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(submittal?.title ?? "");
    setType(submittal?.submittal_type ?? "shop_drawing");
    setDiscipline(submittal?.discipline ?? "other");
    setStatusV(submittal?.status ?? "pending");
    setReference(submittal?.reference ?? "");
    setDate(submittal?.date ?? "");
    setFile(null);
  }, [submittal]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData();
    form.append("title", title);
    form.append("submittal_type", type);
    form.append("discipline", discipline);
    form.append("status", statusV);
    form.append("reference", reference);
    if (date) form.append("date", date);
    if (file) form.append("attachment", file);
    try {
      if (isEdit && submittal) await api.uploadApi(`/projects/${projectId}/submittals/${submittal.id}/`, form, "PATCH");
      else await api.uploadApi(`/projects/${projectId}/submittals/`, form);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <Modal open title={isEdit ? "Edit submittal" : "Add submittal"} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="submittal-form" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
        </>
      }>
      <form id="submittal-form" onSubmit={submit} className={styles.form}>
        <Input label="Title" name="title" required autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
        <Select label="Type" options={TYPES} value={type} onChange={(e) => setType(e.target.value)} />
        <Select label="Discipline" options={DISCIPLINES} value={discipline} onChange={(e) => setDiscipline(e.target.value)} />
        <Select label="Status" options={STATUSES} value={statusV} onChange={(e) => setStatusV(e.target.value)} />
        <Input label="Reference no. (optional)" name="reference" value={reference} onChange={(e) => setReference(e.target.value)} />
        <Input label="Submission date" name="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <label className={styles.fileLabel}>
          <span>Attachment (optional)</span>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {isEdit && submittal?.has_attachment && !file && <p className={styles.muted}>An attachment is already present. Choosing a file replaces it.</p>}
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
