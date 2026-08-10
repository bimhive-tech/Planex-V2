"use client";

// Add/edit form for one Part Scope entry.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import type { PartScope } from "@/types/project";
import formStyles from "./projectForm.module.css";

export function PartScopeModal({ projectId, entry, onClose, onSaved }: {
  projectId: string; entry: PartScope | null; onClose: () => void; onSaved: () => void;
}) {
  const isEdit = !!entry;
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [startDate, setStartDate] = useState("");
  const [completionRevised, setCompletionRevised] = useState("");
  const [forecastCompletion, setForecastCompletion] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(entry?.title ?? "");
    setAmount(entry?.amount ?? "");
    setStartDate(entry?.start_date ?? "");
    setCompletionRevised(entry?.completion_revised ?? "");
    setForecastCompletion(entry?.forecast_completion ?? "");
    setNotes(entry?.notes ?? "");
  }, [entry]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const body = {
      title, amount: amount || null, start_date: startDate || null,
      completion_revised: completionRevised || null, forecast_completion: forecastCompletion || null,
      notes,
    };
    try {
      if (isEdit && entry) {
        await api.patch(`/projects/${projectId}/part-scopes/${entry.id}/`, body);
      } else {
        await api.post(`/projects/${projectId}/part-scopes/`, body);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <Modal open title={isEdit ? "Edit Part Scope entry" : "Add Part Scope entry"} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="part-scope-form" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
        </>
      }>
      <form id="part-scope-form" onSubmit={submit} className={formStyles.form}>
        <Input label="Title" name="title" required autoFocus placeholder="e.g. Elevator Package"
          value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input label="Amount" name="amount" type="number" step="0.01"
          value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Input label="Start date" name="start_date" type="date"
          value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        <div className={formStyles.row2}>
          <Input label="Completion (revised baseline)" name="completion_revised" type="date"
            value={completionRevised} onChange={(e) => setCompletionRevised(e.target.value)} />
          <Input label="Forecasted completion" name="forecast_completion" type="date"
            value={forecastCompletion} onChange={(e) => setForecastCompletion(e.target.value)} />
        </div>
        <Input label="Notes" name="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
