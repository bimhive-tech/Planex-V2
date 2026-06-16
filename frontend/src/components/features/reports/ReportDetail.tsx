"use client";

// Report Builder: one page to assign the project (pulls its data) + template,
// set the date/period, type the description, manage images (cover / progress /
// attachments), and see a live PDF preview. Mirrors the Template Builder.
import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { API_BASE, ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import type { ProjectListRow } from "@/types/project";
import type { ReportRow, ReportStatus, ReportTemplate } from "@/types/report";
import { ReportAssets } from "./ReportAssets";
import styles from "./reports.module.css";

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "submitted", label: "Submitted" },
  { value: "approved", label: "Approved" },
];
const STATUS_TONE: Record<ReportStatus, "neutral" | "info" | "success"> = {
  draft: "neutral", submitted: "info", approved: "success",
};

type Form = {
  project: string; template: string; title: string; report_number: string;
  report_date: string; period_start: string; period_finish: string; status: string; description: string;
};

export function ReportDetail({ reportId, canManage }: { reportId: string; canManage: boolean }) {
  const [previewKey, setPreviewKey] = useState(0);
  const [form, setForm] = useState<Form | null>(null);
  const [projects, setProjects] = useState<ProjectListRow[]>([]);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { loading, error, reload } = useFetch(async () => {
    const [r, ps, ts] = await Promise.all([
      api.get<ReportRow>(`/reports/${reportId}/`),
      api.get<Paginated<ProjectListRow>>("/projects/?status=all"),
      api.get<Paginated<ReportTemplate>>("/report-templates/"),
    ]);
    setProjects(ps.results);
    setTemplates(ts.results);
    setForm({
      project: r.project, template: r.template ?? "",
      title: r.title, report_number: r.report_number ?? "", report_date: r.report_date ?? "",
      period_start: r.period_start ?? "", period_finish: r.period_finish ?? "",
      status: r.status, description: r.description ?? "",
    });
    return r;
  }, [reportId]);

  const projectOptions = useMemo(
    () => projects.map((p) => ({ value: p.id, label: p.name })),
    [projects],
  );
  const templateOptions = useMemo(
    () => [{ value: "", label: "Default styling" }, ...templates.map((t) => ({ value: t.id, label: t.name }))],
    [templates],
  );

  const pdfUrl = `${API_BASE}/reports/${reportId}/pdf/`;
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm((f) => (f ? { ...f, [k]: e.target.value } : f));
    setSaved(false);
  };

  async function save() {
    if (!form) return;
    setSaving(true);
    setSaved(false);
    setSaveError(null);
    try {
      await api.patch(`/reports/${reportId}/`, {
        ...form,
        template: form.template || null,
        report_date: form.report_date || null,
        period_start: form.period_start || null,
        period_finish: form.period_finish || null,
      });
      setSaved(true);
      setPreviewKey((k) => k + 1); // reflect new project data / styling
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save report.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.page}>
      <Link href={ROUTES.reports} className={styles.back}>
        <Icon name="chevronDown" size={16} style={{ transform: "rotate(90deg)" }} />
        Back to Reports
      </Link>

      <StateView loading={loading} error={error} isEmpty={!form} onRetry={reload}>
        {form && (
          <>
            <header className={styles.head}>
              <div className={styles.headRow}>
                <div>
                  <h1 className={styles.title}>{form.title || "Report"}</h1>
                  <Badge tone={STATUS_TONE[form.status as ReportStatus] ?? "neutral"}>{form.status}</Badge>
                </div>
                <div className={styles.detailActions}>
                  {canManage && <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save report"}</Button>}
                  <Button variant="secondary" leadingIcon={<Icon name="download" size={16} />}
                    onClick={() => window.open(pdfUrl, "_blank", "noopener")}>
                    Open / download PDF
                  </Button>
                  {saved && <span className={styles.assetTag}>Saved</span>}
                </div>
              </div>
            </header>

            <div className={styles.detailGrid}>
              <div>
                {canManage && (
                  <section className={styles.editCard}>
                    <div className={styles.fieldRow}>
                      <Select label="Project (data source)" name="project" options={projectOptions} value={form.project} onChange={set("project")} />
                      <Select label="Template (design)" name="template" options={templateOptions} value={form.template} onChange={set("template")} />
                    </div>
                    <div className={styles.fieldRow}>
                      <Input label="Title" name="title" value={form.title} onChange={set("title")} />
                      <Input label="Report number" name="report_number" value={form.report_number} onChange={set("report_number")} />
                    </div>
                    <div className={styles.fieldRow}>
                      <Input label="Report date" name="report_date" type="date" value={form.report_date} onChange={set("report_date")} />
                      <Select label="Status" name="status" options={STATUS_OPTIONS} value={form.status} onChange={set("status")} />
                    </div>
                    <div className={styles.fieldRow}>
                      <Input label="Period start" name="period_start" type="date" value={form.period_start} onChange={set("period_start")} />
                      <Input label="Period finish" name="period_finish" type="date" value={form.period_finish} onChange={set("period_finish")} />
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label} htmlFor="description">Description (one line per bullet)</label>
                      <textarea id="description" className={styles.textarea} value={form.description}
                        onChange={set("description")} placeholder="وصف المشروع — اكتب كل نقطة في سطر…" />
                      <span className={styles.hint}>Shown in the «Project Description» section. Falls back to the project description when empty.</span>
                    </div>
                    {saveError && <p className="formError">{saveError}</p>}
                    <div className={styles.detailActions}>
                      <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save report"}</Button>
                      {saved && <span className={styles.assetTag}>Saved</span>}
                    </div>
                  </section>
                )}
                <ReportAssets reportId={reportId} canManage={canManage} onChanged={() => setPreviewKey((k) => k + 1)} />
              </div>

              <iframe key={previewKey} className={styles.previewFrame} src={pdfUrl} title="Report PDF preview" />
            </div>
          </>
        )}
      </StateView>
    </div>
  );
}
