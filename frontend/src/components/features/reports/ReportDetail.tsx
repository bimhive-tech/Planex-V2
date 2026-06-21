"use client";

// Report Builder: page-type sub-tabs (Setup, Cover, Project Info, Description,
// Progress Report, Progress Images, Attachments), live project data on the
// read-only tabs, and a real-time PDF preview (debounced auto-save → re-render).
import Link from "next/link";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

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
import type { ReportData, ReportRow, ReportStatus, ReportTemplate } from "@/types/report";
import { ReportAssets } from "./ReportAssets";
import styles from "./reports.module.css";

// pdf.js viewer uses canvas/DOM — load it client-side only (no SSR).
const PdfViewer = dynamic(() => import("./PdfViewer").then((m) => m.PdfViewer), { ssr: false });

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "submitted", label: "Submitted" },
  { value: "approved", label: "Approved" },
];
const STATUS_TONE: Record<ReportStatus, "neutral" | "info" | "success"> = {
  draft: "neutral", submitted: "info", approved: "success",
};
const TABS = [
  { key: "setup", label: "Setup" },
  { key: "scope", label: "Scope" },
  { key: "cover", label: "Cover" },
  { key: "info", label: "Project Info" },
  { key: "description", label: "Description" },
  { key: "progress", label: "Progress Report" },
  { key: "photos", label: "Progress Images" },
  { key: "attachments", label: "Attachments" },
] as const;

// Maps a builder tab to the PDF section anchor it scrolls the preview to.
const TAB_ANCHOR: Record<string, string> = {
  setup: "tab_cover", scope: "tab_cover", cover: "tab_cover",
  info: "tab_info", description: "tab_description",
  progress: "tab_progress", photos: "tab_photos", attachments: "tab_attachments",
};

type Form = {
  project: string; template: string; title: string; report_number: string;
  report_date: string; period_start: string; period_finish: string; status: string; description: string;
};

const fmtDate = (d: string | null) =>
  d ? new Date(d).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "—";

export function ReportDetail({ reportId, canManage }: { reportId: string; canManage: boolean }) {
  const [form, setForm] = useState<Form | null>(null);
  const [scopeIds, setScopeIds] = useState<string[]>([]);
  const [zones, setZones] = useState<{ id: string; name: string }[]>([]);
  const [projects, setProjects] = useState<ProjectListRow[]>([]);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("setup");
  const [refreshKey, setRefreshKey] = useState(0);
  const [data, setData] = useState<ReportData | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewLoading, setPreviewLoading] = useState(true);
  const [sectionPages, setSectionPages] = useState<Record<string, number>>({});
  const [scrollNonce, setScrollNonce] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(true);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { loading, error, reload } = useFetch(async () => {
    const [r, ps, ts] = await Promise.all([
      api.get<ReportRow>(`/reports/${reportId}/`),
      api.get<Paginated<ProjectListRow>>("/projects/?status=all"),
      api.get<Paginated<ReportTemplate>>("/report-templates/"),
    ]);
    setProjects(ps.results);
    setTemplates(ts.results);
    setScopeIds(r.scope_ids ?? []);
    setForm({
      project: r.project, template: r.template ?? "",
      title: r.title, report_number: r.report_number ?? "", report_date: r.report_date ?? "",
      period_start: r.period_start ?? "", period_finish: r.period_finish ?? "",
      status: r.status, description: r.description ?? "",
    });
    return r;
  }, [reportId]);

  const pdfUrl = `${API_BASE}/reports/${reportId}/pdf/`;

  // Live project data (progress tables / info) — refetched after each save.
  useEffect(() => {
    let alive = true;
    api.get<ReportData>(`/reports/${reportId}/data/`).then((d) => alive && setData(d)).catch(() => {});
    return () => { alive = false; };
  }, [reportId, refreshKey]);

  // Real-time preview: fetch the PDF as a blob (bypasses X-Frame-Options).
  useEffect(() => {
    let revoked = false;
    let objectUrl = "";
    setPreviewLoading(true);
    fetch(pdfUrl, { credentials: "include" })
      .then((r) => {
        if (!r.ok) return Promise.reject(new Error("preview failed"));
        const hdr = r.headers.get("X-Section-Pages");  // section -> page map
        if (hdr) { try { setSectionPages(JSON.parse(hdr)); } catch { /* ignore */ } }
        return r.blob();
      })
      .then((blob) => { if (!revoked) { objectUrl = URL.createObjectURL(blob); setPreviewUrl(objectUrl); } })
      .catch(() => setPreviewUrl(""))
      .finally(() => !revoked && setPreviewLoading(false));
    return () => { revoked = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [pdfUrl, refreshKey]);

  // The chosen project's zones, for the Scope tab.
  useEffect(() => {
    if (!form?.project) return;
    let alive = true;
    api.get<{ id: string; name: string }[]>(`/projects/${form.project}/project-zones/`)
      .then((z) => alive && setZones(z)).catch(() => alive && setZones([]));
    return () => { alive = false; };
  }, [form?.project]);

  const save = useCallback(async () => {
    if (!form) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.patch(`/reports/${reportId}/`, {
        ...form,
        scope_ids: scopeIds,
        template: form.template || null,
        report_date: form.report_date || null,
        period_start: form.period_start || null,
        period_finish: form.period_finish || null,
      });
      setSaved(true);
      setRefreshKey((k) => k + 1); // save → re-pull data + re-render the preview
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save report.");
    } finally {
      setSaving(false);
    }
  }, [form, reportId, scopeIds]);

  const projectOptions = useMemo(() => projects.map((p) => ({ value: p.id, label: p.name })), [projects]);
  const templateOptions = useMemo(
    () => [{ value: "", label: "Default styling" }, ...templates.map((t) => ({ value: t.id, label: t.name }))],
    [templates],
  );

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm((f) => (f ? { ...f, [k]: e.target.value } : f));
    setSaved(false);
  };
  const bump = () => setRefreshKey((k) => k + 1);

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
                  <Badge tone={STATUS_TONE[form.status as ReportStatus] ?? "neutral"}>
                    {saving ? "Saving…" : saved ? "Saved" : "Unsaved"}
                  </Badge>
                </div>
                <div className={styles.detailActions}>
                  {canManage && <Button onClick={save} disabled={saving}>Save report</Button>}
                  <Button variant="secondary" leadingIcon={<Icon name="download" size={16} />}
                    onClick={() => window.open(pdfUrl, "_blank", "noopener")}>
                    Open / download PDF
                  </Button>
                </div>
              </div>
            </header>

            <div className={styles.detailGrid}>
              <div className={styles.builderCol}>
                <nav className={styles.tabs}>
                  {TABS.map((t) => (
                    <button key={t.key} type="button"
                      className={`${styles.tab} ${t.key === tab ? styles.tabActive : ""}`}
                      onClick={() => { setTab(t.key); setScrollNonce((n) => n + 1); }}>
                      {t.label}
                    </button>
                  ))}
                </nav>
                {tab === "setup" && canManage && (
                  <section className={styles.tabPanel}>
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
                  </section>
                )}

                {tab === "scope" && (
                  <section className={styles.tabPanel}>
                    <h2 className={styles.panelTitle}>Zones to include</h2>
                    <p className={styles.hint}>Tick the zones this report covers. Leave all unticked to include the whole project.</p>
                    {zones.map((z) => {
                      const checked = scopeIds.includes(z.id);
                      return (
                        <label key={z.id} className={styles.scopeRow}>
                          <input type="checkbox" checked={checked} disabled={!canManage}
                            onChange={(e) => setScopeIds((ids) =>
                              e.target.checked ? [...ids, z.id] : ids.filter((i) => i !== z.id))} />
                          {z.name}
                        </label>
                      );
                    })}
                    {zones.length === 0 && <p className={styles.hint}>No zones in this project.</p>}
                  </section>
                )}

                {tab === "cover" && (
                  <ReportAssets reportId={reportId} canManage={canManage} only="cover" onChanged={bump} />
                )}

                {tab === "info" && (
                  <section className={styles.tabPanel}>
                    <h2 className={styles.panelTitle}>Project information (from {data?.project.name ?? "the project"})</h2>
                    <table className={styles.dataTable}>
                      <tbody>
                        {data && ([
                          ["Client", data.project.client], ["Consultant", data.project.consultant],
                          ["Contractor", data.project.contractor], ["Type", data.project.type],
                          ["Location", data.project.location],
                          ["Value", data.project.budget ? `${data.project.budget} ${data.project.currency}` : "—"],
                          ["Planned start", fmtDate(data.project.planned_start)],
                          ["Planned finish", fmtDate(data.project.planned_finish)],
                          ["Built-up area (m²)", data.project.size_sqm ?? "—"],
                        ] as [string, string][]).map(([k, v]) => (
                          <tr key={k}><th>{k}</th><td>{v || "—"}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </section>
                )}

                {tab === "description" && canManage && (
                  <section className={styles.tabPanel}>
                    <label className={styles.label} htmlFor="description">Description (one line per bullet)</label>
                    <textarea id="description" className={styles.textarea} value={form.description}
                      onChange={set("description")} placeholder="وصف المشروع — اكتب كل نقطة في سطر…" />
                    <span className={styles.hint}>Shown in the «Project Description» section; falls back to the project description when empty. Formatting (align, size, color, bold, underline, bullets) is in the Template Builder → Description tab.</span>
                  </section>
                )}

                {tab === "progress" && (
                  <section className={styles.tabPanel}>
                    <h2 className={styles.panelTitle}>Overall progress</h2>
                    <div className={styles.bigStat}>{data ? `${data.overall.toFixed(1)}%` : "…"}</div>
                    {data && (
                      <div className={styles.statRow}>
                        <div className={styles.statChip}><strong>{data.breakdown.completed}</strong><span>Completed</span></div>
                        <div className={styles.statChip}><strong>{data.breakdown.in_progress}</strong><span>In progress</span></div>
                        <div className={styles.statChip}><strong>{data.breakdown.not_started}</strong><span>Not started</span></div>
                      </div>
                    )}
                    <h2 className={styles.panelTitle}>Progress by zone</h2>
                    <table className={styles.dataTable}>
                      <thead><tr><th>Zone</th><th>Progress</th></tr></thead>
                      <tbody>
                        {data?.zones.length
                          ? data.zones.map((z) => <tr key={z.name}><th>{z.name}</th><td>{z.progress.toFixed(1)}%</td></tr>)
                          : <tr><td colSpan={2}>No zones in this project yet.</td></tr>}
                      </tbody>
                    </table>
                  </section>
                )}

                {tab === "photos" && (
                  <ReportAssets reportId={reportId} canManage={canManage} only="progress" onChanged={bump} />
                )}
                {tab === "attachments" && (
                  <ReportAssets reportId={reportId} canManage={canManage} only="attachment" onChanged={bump} />
                )}

                {saveError && <p className="formError">{saveError}</p>}
              </div>

              <PdfViewer url={previewUrl} loading={previewLoading}
                scrollToPage={sectionPages[TAB_ANCHOR[tab]]} scrollNonce={scrollNonce}
                onDownload={() => window.open(pdfUrl, "_blank", "noopener")} />
            </div>
          </>
        )}
      </StateView>
    </div>
  );
}
