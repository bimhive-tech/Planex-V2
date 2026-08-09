"use client";

// Create / edit a project in a right-side drawer. Grouped sections keep the
// (fairly long) descriptive form scannable.
import { useEffect, useState } from "react";

import { Drawer } from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError } from "@/lib/api";
import { useCurrencies, useProjectPriorities, useProjectTypes } from "@/hooks/useMasterData";
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
  "name", "code", "project_type", "priority", "location", "description",
  "budget", "currency", "advance_payment", "client_name",
  "consultant_name", "consultant_phone", "consultant_email",
  "contractor_name", "contractor_phone", "contractor_email", "contractor_consultant",
  "planned_start", "planned_finish", "revised_finish", "forecast_finish", "project_delay_days",
  "eot_days", "size_sqm", "notes", "contract_value", "approved_value", "forecast_cost", "revised_amount",
  "part_amount", "part_completion_revised", "part_forecast_completion", "part_delay_days",
];

const blank = (): Form => {
  const f: Form = {};
  FIELDS.forEach((k) => (f[k] = ""));
  return f;
};

export function ProjectFormDrawer({ open, projectId, onClose, onSaved }: Props) {
  const isEdit = !!projectId;
  const [form, setForm] = useState<Form>(blank);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: typesData } = useProjectTypes();
  const { data: prioritiesData } = useProjectPriorities();
  const { data: currenciesData } = useCurrencies();
  const typeOptions = (typesData?.results ?? []).map((t) => ({ value: t.name, label: t.name }));
  const priorityOptions = (prioritiesData?.results ?? []).map((p) => ({ value: p.name, label: p.name }));
  const currencyOptions = (currenciesData?.results ?? [])
    .map((c) => ({ value: c.code, label: `${c.code} — ${c.name}` }));

  // A brand-new project has no stored value yet — default it to this
  // company's own first option (Master Data is company-editable, so there's
  // no longer a single hardcoded default that's always valid) once each list
  // has loaded, without clobbering a value the user already picked.
  useEffect(() => {
    if (isEdit || !open) return;
    if (!form.project_type && typeOptions.length) setForm((f) => ({ ...f, project_type: typeOptions[0].value }));
  }, [isEdit, open, typeOptions, form.project_type]);
  useEffect(() => {
    if (isEdit || !open) return;
    if (!form.priority && priorityOptions.length) setForm((f) => ({ ...f, priority: priorityOptions[0].value }));
  }, [isEdit, open, priorityOptions, form.priority]);
  useEffect(() => {
    if (isEdit || !open || form.currency || !currencyOptions.length) return;
    const preferred = currenciesData?.results.find((c) => c.is_default)?.code ?? currencyOptions[0].value;
    setForm((f) => ({ ...f, currency: preferred }));
  }, [isEdit, open, currencyOptions, currenciesData, form.currency]);

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
    for (const k of [
      "planned_start", "planned_finish", "revised_finish", "forecast_finish", "project_delay_days",
      "size_sqm", "budget", "advance_payment", "eot_days",
      "contract_value", "approved_value", "forecast_cost", "revised_amount",
      "part_amount", "part_completion_revised", "part_forecast_completion", "part_delay_days",
    ]) {
      if (!payload[k]) payload[k] = null;
    }
    try {
      const saved = isEdit
        ? await api.patch<ProjectDetail>(`/projects/${projectId}/`, payload)
        : await api.post<ProjectDetail>("/projects/", payload);
      // The drawer doesn't unmount on close (only `open` toggles), so without
      // this the *next* time it opens still shows "Saving…" stuck from here.
      setSubmitting(false);
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
          <Input label="Project code" name="code" placeholder="SCD-2026-001" value={form.code} onChange={set("code")} />
          <Input label="Location" name="location" value={form.location} onChange={set("location")} />
        </div>
        <div className={styles.row2}>
          <Select label="Type" name="project_type"
            options={typeOptions.length ? typeOptions : [{ value: form.project_type, label: "Loading…" }]}
            value={form.project_type} onChange={set("project_type")} />
          <Select label="Priority" name="priority"
            options={priorityOptions.length ? priorityOptions : [{ value: form.priority, label: "Loading…" }]}
            value={form.priority} onChange={set("priority")} />
        </div>
        <div className={styles.row2}>
          <Input label="Budget" name="budget" type="number" step="0.01" value={form.budget} onChange={set("budget")} />
          <Select label="Currency" name="currency"
            options={currencyOptions.length ? currencyOptions : [{ value: form.currency, label: "Loading…" }]}
            value={form.currency} onChange={set("currency")} />
        </div>
        <div className={styles.row2}>
          <Input label="Advance payment" name="advance_payment" type="number" step="0.01"
            value={form.advance_payment} onChange={set("advance_payment")} />
          <Input label="EOT (days)" name="eot_days" type="number" step="1"
            value={form.eot_days} onChange={set("eot_days")} />
        </div>
        <div className={styles.row2}>
          <Input label="Contract value" name="contract_value" type="number" step="0.01"
            value={form.contract_value} onChange={set("contract_value")} />
          <Input label="Approved value" name="approved_value" type="number" step="0.01"
            value={form.approved_value} onChange={set("approved_value")} />
        </div>
        <div className={styles.row2}>
          <Input label="Forecast cost" name="forecast_cost" type="number" step="0.01"
            value={form.forecast_cost} onChange={set("forecast_cost")} />
          <Input label="Revised amount" name="revised_amount" type="number" step="0.01"
            value={form.revised_amount} onChange={set("revised_amount")} />
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
          <Input label="Forecast finish" name="forecast_finish" type="date" value={form.forecast_finish} onChange={set("forecast_finish")} />
        </div>
        <div className={styles.row2}>
          <Input label="Size (sqm)" name="size_sqm" type="number" step="0.01" value={form.size_sqm} onChange={set("size_sqm")} />
          <Input label="Project delay (calendar days)" name="project_delay_days" type="number" step="1"
            value={form.project_delay_days} onChange={set("project_delay_days")} />
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
        <Input label="Contractor's consultant" name="contractor_consultant"
          value={form.contractor_consultant} onChange={set("contractor_consultant")} />

        <p className={styles.section}>Part (contracted sub-scope)</p>
        <p className={styles.sectionHint}>
          Only fill these in if this contract tracks a specific "Part" of the work alongside the whole project.
        </p>
        <Input label="Part amount" name="part_amount" type="number" step="0.01"
          value={form.part_amount} onChange={set("part_amount")} />
        <div className={styles.row2}>
          <Input label="Part completion (revised baseline)" name="part_completion_revised" type="date"
            value={form.part_completion_revised} onChange={set("part_completion_revised")} />
          <Input label="Part forecasted completion" name="part_forecast_completion" type="date"
            value={form.part_forecast_completion} onChange={set("part_forecast_completion")} />
        </div>
        <Input label="Part delay (calendar days)" name="part_delay_days" type="number" step="1"
          value={form.part_delay_days} onChange={set("part_delay_days")} />

        <div className={styles.field}>
          <label className={styles.label} htmlFor="notes">Notes</label>
          <textarea id="notes" className={styles.textarea} rows={2} value={form.notes} onChange={set("notes")} />
        </div>

        {error && <p className="formError">{error}</p>}
      </form>
    </Drawer>
  );
}
