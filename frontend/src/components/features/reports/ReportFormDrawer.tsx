"use client";

// "New report" drawer — the minimal step to create a draft: assign a project
// (its data source) and a title. Everything else (date, description, images,
// template tweaks) is done on the Report Builder, where this navigates next.
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Drawer } from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api, ApiError, type Paginated } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import type { ProjectListRow } from "@/types/project";
import type { ReportRow, ReportTemplate } from "@/types/report";
import styles from "./reports.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ReportFormDrawer({ open, onClose }: Props) {
  const router = useRouter();
  const [project, setProject] = useState("");
  const [template, setTemplate] = useState("");
  const [title, setTitle] = useState("Monthly Progress Report");
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
        if (!project && p.results[0]) setProject(p.results[0].id);
        const def = t.results.find((x) => x.is_default) ?? t.results[0];
        if (!template && def) setTemplate(def.id);
      })
      .catch(() => setError("Couldn't load projects or templates."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const projectOptions = useMemo(
    () => [{ value: "", label: "Select a project…" }, ...projects.map((p) => ({ value: p.id, label: p.name }))],
    [projects],
  );
  const templateOptions = useMemo(
    () => [{ value: "", label: "Default styling" }, ...templates.map((t) => ({ value: t.id, label: t.name }))],
    [templates],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.post<ReportRow>("/reports/", {
        project, title, template: template || null,
      });
      router.push(`${ROUTES.reports}/${created.id}`); // straight into the builder
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create report.");
      setSubmitting(false);
    }
  }

  return (
    <Drawer
      open={open}
      title="New report"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="report-form" disabled={submitting || !project}>
            {submitting ? "Creating…" : "Create & open builder"}
          </Button>
        </>
      }
    >
      <form id="report-form" onSubmit={handleSubmit} className={styles.drawerForm}>
        <Select label="Project (data source)" name="project" required options={projectOptions} value={project} onChange={(e) => setProject(e.target.value)} />
        <Select label="Template (design)" name="template" options={templateOptions} value={template} onChange={(e) => setTemplate(e.target.value)} />
        <Input label="Title" name="title" required value={title} onChange={(e) => setTitle(e.target.value)} />
        <p className={styles.hint}>You&apos;ll set the date, description, and images in the builder next.</p>
        {error && <p className="formError">{error}</p>}
      </form>
    </Drawer>
  );
}
