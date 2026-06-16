"use client";

// Create / edit a report: pick a project + template, set title, number, and the
// reporting period. The PDF is generated on demand from the saved report.
import { useEffect, useMemo, useState } from "react";

import { Drawer } from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError, type Paginated } from "@/lib/api";
import type { ProjectListRow } from "@/types/project";
import type { ReportRow, ReportTemplate } from "@/types/report";
import styles from "./reports.module.css";

interface Props {
  open: boolean;
  reportId: string | null;
  onClose: () => void;
  onSaved: () => void;
}

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "submitted", label: "Submitted" },
  { value: "approved", label: "Approved" },
];

const blank = () => ({
  project: "",
  template: "",
  title: "Monthly Progress Report",
  report_number: "",
  period_start: "",
  period_finish: "",
  status: "draft",
});

export function ReportFormDrawer({ open, reportId, onClose, onSaved }: Props) {
  const isEdit = !!reportId;
  const [form, setForm] = useState(blank);
  const [projects, setProjects] = useState<ProjectListRow[]>([]);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    Promise.all([
      api.get<Paginated<ProjectListRow>>("/projects/?status=all"),
      api.get<Paginated<ReportTemplate>>("/report-templates/"),
    ])
      .then(([p, t]) => {
        setProjects(p.results);
        setTemplates(t.results);
      })
      .catch(() => setError("Couldn't load projects or templates."));

    if (reportId) {
      api
        .get<ReportRow>(`/reports/${reportId}/`)
        .then((r) =>
          setForm({
            project: r.project,
            template: r.template ?? "",
            title: r.title,
            report_number: r.report_number ?? "",
            period_start: r.period_start ?? "",
            period_finish: r.period_finish ?? "",
            status: r.status,
          }),
        )
        .catch(() => setError("Couldn't load this report."));
    } else {
      setForm(blank());
    }
  }, [open, reportId]);

  const projectOptions = useMemo(
    () => [{ value: "", label: "Select a project…" }, ...projects.map((p) => ({ value: p.id, label: p.name }))],
    [projects],
  );
  const templateOptions = useMemo(
    () => [{ value: "", label: "Default styling" }, ...templates.map((t) => ({ value: t.id, label: t.name }))],
    [templates],
  );

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const payload: Record<string, unknown> = {
      ...form,
      template: form.template || null,
      period_start: form.period_start || null,
      period_finish: form.period_finish || null,
    };
    try {
      if (isEdit) await api.patch(`/reports/${reportId}/`, payload);
      else await api.post("/reports/", payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save report.");
      setSubmitting(false);
    }
  }

  return (
    <Drawer
      open={open}
      title={isEdit ? "Edit report" : "New report"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="report-form" disabled={submitting}>
            {submitting ? "Saving…" : isEdit ? "Save report" : "Create report"}
          </Button>
        </>
      }
    >
      <form id="report-form" onSubmit={handleSubmit} className={styles.drawerForm}>
        <Select label="Project" name="project" required options={projectOptions} value={form.project} onChange={set("project")} />
        <Select label="Template" name="template" options={templateOptions} value={form.template} onChange={set("template")} />
        <Input label="Title" name="title" required value={form.title} onChange={set("title")} />
        <Input label="Report number" name="report_number" placeholder="52" value={form.report_number} onChange={set("report_number")} />
        <Input label="Period start" name="period_start" type="date" value={form.period_start} onChange={set("period_start")} />
        <Input label="Period finish" name="period_finish" type="date" value={form.period_finish} onChange={set("period_finish")} />
        <Select label="Status" name="status" options={STATUS_OPTIONS} value={form.status} onChange={set("status")} />
        {error && <p className="formError">{error}</p>}
      </form>
    </Drawer>
  );
}
