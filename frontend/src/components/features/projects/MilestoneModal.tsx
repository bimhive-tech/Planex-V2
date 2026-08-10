"use client";

// Add/edit form for a single milestone — shared by the Overview highlights
// card and the full Milestones tab.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { MILESTONE_STATUSES, type Milestone } from "./milestoneShared";
import styles from "./milestones.module.css";

export function MilestoneModal({ projectId, milestone, onClose, onSaved }: {
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
        <Select label="Status" options={MILESTONE_STATUSES} value={statusV} onChange={(e) => setStatusV(e.target.value)} />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
