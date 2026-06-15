"use client";

// Create / edit an activity (BOQ item) under a scope.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError } from "@/lib/api";
import type { Activity } from "@/types/project";
import styles from "./projectForm.module.css";

const PROGRESS_TYPES = [
  { value: "percentage", label: "Percentage" },
  { value: "quantity", label: "Quantity" },
];

interface Props {
  open: boolean;
  projectId: string;
  scopeId: string; // parent scope (create)
  activity: Activity | null; // edit when set
  onClose: () => void;
  onSaved: () => void;
}

interface Form {
  name: string;
  code: string;
  unit: string;
  progress_type: string;
  planned_quantity: string;
  weight: string;
  progress_percent: string;
}

const EMPTY: Form = {
  name: "", code: "", unit: "", progress_type: "percentage",
  planned_quantity: "", weight: "1", progress_percent: "0",
};

export function ActivityFormModal({ open, projectId, scopeId, activity, onClose, onSaved }: Props) {
  const isEdit = !!activity;
  const [form, setForm] = useState<Form>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setForm(activity
        ? { name: activity.name, code: activity.code, unit: activity.unit,
            progress_type: activity.progress_type, planned_quantity: activity.planned_quantity ?? "",
            weight: activity.weight, progress_percent: activity.progress_percent }
        : EMPTY);
      setError(null);
    }
  }, [open, activity]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const payload: Record<string, unknown> = { ...form, scope: scopeId };
    if (!payload.planned_quantity) payload.planned_quantity = null;
    try {
      if (isEdit && activity) {
        await api.patch(`/projects/${projectId}/activities/${activity.id}/`, payload);
      } else {
        await api.post(`/projects/${projectId}/activities/`, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save activity.");
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={isEdit ? "Edit activity" : "Add activity"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="activity-form" disabled={submitting}>
            {submitting ? "Saving…" : isEdit ? "Save" : "Add"}
          </Button>
        </>
      }
    >
      <form id="activity-form" onSubmit={handleSubmit} className={styles.form}>
        <Input label="Activity name" name="name" required autoFocus
          placeholder="e.g. Excavation" value={form.name} onChange={set("name")} />
        <div className={styles.row2}>
          <Input label="Code" name="code" value={form.code} onChange={set("code")} />
          <Input label="Unit" name="unit" placeholder="m³, m², no." value={form.unit} onChange={set("unit")} />
        </div>
        <div className={styles.row2}>
          <Select label="Tracked by" options={PROGRESS_TYPES} value={form.progress_type} onChange={set("progress_type")} />
          <Input label="Planned quantity" name="planned_quantity" type="number" step="0.01"
            value={form.planned_quantity} onChange={set("planned_quantity")} />
        </div>
        <div className={styles.row2}>
          <Input label="Weight" name="weight" type="number" step="0.01" value={form.weight} onChange={set("weight")} />
          <Input label="Progress %" name="progress_percent" type="number" step="0.1" min="0" max="100"
            value={form.progress_percent} onChange={set("progress_percent")} />
        </div>
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
