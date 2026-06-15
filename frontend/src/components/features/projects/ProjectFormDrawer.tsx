"use client";

// Create / edit a project in a right-side drawer. Grouped sections keep the
// (fairly long) descriptive form scannable.
import { useEffect, useState } from "react";

import { Drawer } from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError } from "@/lib/api";
import { PROJECT_TYPES } from "@/lib/projectTypes";
import type { ProjectDetail } from "@/types/project";
import styles from "./projectForm.module.css";

interface Props {
  open: boolean;
  projectId: string | null; // null = create
  onClose: () => void;
  onSaved: (project: ProjectDetail) => void;
}

type Form = Record<string, string>;

const FIELDS = [
  "name", "project_type", "location", "description", "client_name",
  "consultant_name", "consultant_phone", "consultant_email",
  "contractor_name", "contractor_phone", "contractor_email",
  "planned_start", "planned_finish", "revised_finish", "size_sqm", "notes",
];

const blank = (): Form => {
  const f: Form = {};
  FIELDS.forEach((k) => (f[k] = ""));
  f.project_type = "commercial";
  return f;
};

export function ProjectFormDrawer({ open, projectId, onClose, onSaved }: Props) {
  const isEdit = !!projectId;
  const [form, setForm] = useState<Form>(blank);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (projectId) {
      setLoading(true);
      api
        .get<ProjectDetail>(`/projects/${projectId}/`)
        .then((p) => {
          const f = blank();
          FIELDS.forEach((k) => (f[k] = (p as unknown as Record<string, unknown>)[k]?.toString() ?? ""));
          setForm(f);
        })
        .catch(() => setError("Couldn't load this project."))
        .finally(() => setLoading(false));
    } else {
      setForm(blank());
    }
  }, [open, projectId]);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    // Empty dates / size must be null, not "".
    const payload: Record<string, unknown> = { ...form };
    for (const k of ["planned_start", "planned_finish", "revised_finish", "size_sqm"]) {
      if (!payload[k]) payload[k] = null;
    }
    try {
      const saved = isEdit
        ? await api.patch<ProjectDetail>(`/projects/${projectId}/`, payload)
        : await api.post<ProjectDetail>("/projects/", payload);
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save project.");
      setSubmitting(false);
    }
  }

  return (
    <Drawer
      open={open}
      title={isEdit ? "Edit project" : "New project"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="project-form" disabled={submitting || loading}>
            {submitting ? "Saving…" : isEdit ? "Save project" : "Create project"}
          </Button>
        </>
      }
    >
      <form id="project-form" onSubmit={handleSubmit} className={styles.form}>
        <Input label="Project name" name="name" required autoFocus value={form.name} onChange={set("name")} />
        <div className={styles.row2}>
          <Select label="Type" name="project_type" options={[...PROJECT_TYPES]}
            value={form.project_type} onChange={set("project_type")} />
          <Input label="Location" name="location" value={form.location} onChange={set("location")} />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="description">Description</label>
          <textarea id="description" className={styles.textarea} rows={2}
            value={form.description} onChange={set("description")} />
        </div>

        <p className={styles.section}>Schedule</p>
        <div className={styles.row2}>
          <Input label="Planned start" name="planned_start" type="date" value={form.planned_start} onChange={set("planned_start")} />
          <Input label="Planned finish" name="planned_finish" type="date" value={form.planned_finish} onChange={set("planned_finish")} />
        </div>
        <div className={styles.row2}>
          <Input label="Revised finish" name="revised_finish" type="date" value={form.revised_finish} onChange={set("revised_finish")} />
          <Input label="Size (sqm)" name="size_sqm" type="number" step="0.01" value={form.size_sqm} onChange={set("size_sqm")} />
        </div>

        <p className={styles.section}>Client</p>
        <Input label="Client name" name="client_name" value={form.client_name} onChange={set("client_name")} />

        <p className={styles.section}>Consultant</p>
        <Input label="Name" name="consultant_name" value={form.consultant_name} onChange={set("consultant_name")} />
        <div className={styles.row2}>
          <Input label="Phone" name="consultant_phone" value={form.consultant_phone} onChange={set("consultant_phone")} />
          <Input label="Email" name="consultant_email" type="email" value={form.consultant_email} onChange={set("consultant_email")} />
        </div>

        <p className={styles.section}>Contractor</p>
        <Input label="Name" name="contractor_name" value={form.contractor_name} onChange={set("contractor_name")} />
        <div className={styles.row2}>
          <Input label="Phone" name="contractor_phone" value={form.contractor_phone} onChange={set("contractor_phone")} />
          <Input label="Email" name="contractor_email" type="email" value={form.contractor_email} onChange={set("contractor_email")} />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="notes">Notes</label>
          <textarea id="notes" className={styles.textarea} rows={2} value={form.notes} onChange={set("notes")} />
        </div>

        {error && <p className="formError">{error}</p>}
      </form>
    </Drawer>
  );
}
