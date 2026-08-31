"use client";

// Report Builder: page-type sub-tabs (Setup, Cover, Project Info, Progress
// Report, Progress Images, Attachments), live project data on the read-only
// tabs, and a real-time PDF preview (debounced auto-save → re-render). The
// report's narrative ("Description") is edited directly on the Customize
// tab's canvas, not a tab here — see ElementPreview.tsx's DescriptionPreview.
import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError, type Paginated } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import type { ProjectListRow } from "@/types/project";
import type { ReportData, ReportLayoutOverride, ReportRow, ReportStatus, ReportTemplate } from "@/types/report";
import { ReportAssets } from "./ReportAssets";
import { ReportLayoutEditor } from "./ReportLayoutEditor";
import { ProgressImagePicker } from "./ProgressImagePicker";
import { ProjectReportAssets } from "@/components/features/projects/ProjectReportAssets";
import { ScopeTree } from "./ScopeTree";
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
  { key: "progress", label: "Progress Report" },
  { key: "photos", label: "Progress Images" },
  { key: "attachments", label: "Attachments" },
  { key: "layout", label: "Customize" },
] as const;

// Maps a builder tab to the PDF section anchor it scrolls the preview to.
// No "description" entry — that content now lives entirely as a canvas
// element (edited in place on the Customize tab), not a report-metadata
// field with its own tab.
const TAB_ANCHOR: Record<string, string> = {
  setup: "tab_cover", scope: "tab_cover", cover: "tab_cover",
  info: "tab_info",
  progress: "tab_progress", photos: "tab_photos", attachments: "tab_attachments",
};

type Form = {
  project: string; template: string; title: string; report_number: string;
  report_date: string; period_start: string; period_finish: string; status: string;
};

const fmtDate = (d: string | null) =>
  d ? new Date(d).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "—";

export function ReportDetail({ reportId, canManage }: { reportId: string; canManage: boolean }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [form, setForm] = useState<Form | null>(null);
  const [scopeIds, setScopeIds] = useState<string[]>([]);
  const [projects, setProjects] = useState<ProjectListRow[]>([]);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  // Which builder tab is open survives a refresh via the URL's own `?tab=`
  // — reading it back out of state alone would reset to "setup" on reload.
  const [tab, setTabState] = useState<(typeof TABS)[number]["key"]>(
    () => TABS.find((t) => t.key === searchParams.get("tab"))?.key ?? "setup",
  );
  const setTab = useCallback((next: (typeof TABS)[number]["key"]) => {
    setTabState(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", next);
    router.replace(`?${params.toString()}`, { scroll: false });
  }, [router, searchParams]);
  // True once the Customize tab has been opened at least once — see the
  // ReportLayoutEditor render below for why it then stays mounted.
  const [layoutOpened, setLayoutOpened] = useState(tab === "layout");
  useEffect(() => {
    if (tab === "layout") setLayoutOpened(true);
  }, [tab]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [data, setData] = useState<ReportData | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewLoading, setPreviewLoading] = useState(true);
  const [sectionPages, setSectionPages] = useState<Record<string, number>>({});
  const [scrollNonce, setScrollNonce] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOverride, setSavedOverride] = useState<ReportLayoutOverride | null>(null);

  const { loading, error, reload } = useFetch(async () => {
    const [r, ps, ts] = await Promise.all([
      api.get<ReportRow>(`/reports/${reportId}/`),
      api.get<Paginated<ProjectListRow>>("/projects/?status=all"),
      api.get<Paginated<ReportTemplate>>("/report-templates/"),
    ]);
    setProjects(ps.results);
    setTemplates(ts.results);
    setScopeIds(r.scope_ids ?? []);
    setSavedOverride(r.layout_override ?? null);
    setForm({
      project: r.project, template: r.template ?? "",
      title: r.title, report_number: r.report_number ?? "", report_date: r.report_date ?? "",
      period_start: r.period_start ?? "", period_finish: r.period_finish ?? "",
      status: r.status,
    });
    return r;
  }, [reportId]);

  // Served by the route handler (app/reports/[id]/pdf-file), not the /api rewrite
  // proxy, so long renders of big reports aren't reset mid-flight.
  const pdfUrl = `/reports/${reportId}/pdf-file`;

  // Live project data (progress tables / info) — refetched after each save.
  // Served by the route handler (app/reports/[id]/data-file), not the /api
  // rewrite proxy: build_report_context() alone takes 30s+ on a large report,
  // which the proxy's ~60s limit can reset mid-flight (same fix as pdfUrl).
  useEffect(() => {
    let alive = true;
    setDataLoading(true);
    fetch(`/reports/${reportId}/data-file`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("data fetch failed"))))
      .then((d: ReportData) => alive && setData(d))
      .catch(() => {})
      .finally(() => alive && setDataLoading(false));
    return () => { alive = false; };
  }, [reportId, refreshKey]);

  // Real-time preview: fetch the PDF as a blob (bypasses X-Frame-Options).
  // Skipped on the Customize tab — PdfViewer isn't rendered there (see the
  // detailGridFull branch below), and its canvas already renders live from
  // real project data (see ElementPreview), so there's nothing there that
  // needs this render at all.
  useEffect(() => {
    if (tab === "layout") return;
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
  }, [pdfUrl, refreshKey, tab]);

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
  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === form?.template) ?? null,
    [templates, form?.template],
  );

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setField(k, e.target.value);
  };
  const setField = (k: keyof Form, value: string) => {
    setForm((f) => (f ? { ...f, [k]: value } : f));
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

            <div className={`${styles.detailGrid} ${tab === "layout" ? styles.detailGridFull : ""}`}>
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
                    <p className="formHint">Progress is shown as of the report date — each task uses its latest dated entry on or before this day.</p>
                    <div className={styles.fieldRow}>
                      <Input label="Period start" name="period_start" type="date" value={form.period_start} onChange={set("period_start")} />
                      <Input label="Period finish" name="period_finish" type="date" value={form.period_finish} onChange={set("period_finish")} />
                    </div>
                    {/* Project logos — shown on every report's cover for this project.
                        (Cover image and photos have their own sub-tabs.) */}
                    {form.project && (
                      <ProjectReportAssets
                        projectId={form.project}
                        canManage={canManage}
                        onChanged={bump}
                        types={["logo_left", "logo_right", "logo"]}
                        title="Logos"
                        subtitle="Left and right header logos, plus any number of additional partner logos, shown on every report for this project."
                      />
                    )}
                  </section>
                )}

                {tab === "scope" && (
                  <section className={styles.tabPanel}>
                    <h2 className={styles.panelTitle}>What to include</h2>
                    <p className={styles.hint}>Tick zones, subzones, phases, or tasks. Ticking a node includes everything under it. Leave all unticked to include the whole project.</p>
                    {form.project && (
                      <ScopeTree projectId={form.project} selectedIds={scopeIds} canManage={canManage}
                        onToggle={(id) => setScopeIds((ids) => ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id])} />
                    )}
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
                  <section className={styles.tabPanel}>
                    <ProgressImagePicker reportId={reportId} canManage={canManage} onChanged={bump} />
                    <hr className={styles.divider} />
                    <ReportAssets reportId={reportId} canManage={canManage} only="progress" onChanged={bump} />
                  </section>
                )}
                {tab === "attachments" && (
                  <ReportAssets reportId={reportId} canManage={canManage} only="attachment" onChanged={bump} />
                )}

                {/* Stays MOUNTED once opened, hidden rather than unmounted, so
                    switching to another tab and back doesn't throw away every
                    unsaved page edit — the editor holds its whole draft
                    (pages, master elements, dirty flag) in local state, and a
                    conditional render silently destroyed all of it on any tab
                    click, with no warning (2026-08-30). Never mounted at all
                    until the tab is first opened, so a report the user only
                    reads doesn't pay for the editor's live-preview fetches. */}
                {layoutOpened && (
                  <div hidden={tab !== "layout"}>
                  <ReportLayoutEditor
                    // `data` arrives from a separate fetch and can resolve after this
                    // tab first mounts; remount once it does so the starting page
                    // list expands repeating pages instead of freezing on 13 raw types.
                    key={`${reportId}-${form.template}-${data ? "live" : "pending"}`}
                    reportId={reportId}
                    template={selectedTemplate}
                    savedOverride={savedOverride}
                    liveData={data}
                    liveDataLoading={dataLoading}
                    canManage={canManage}
                    onSaved={() => { reload(); bump(); }}
                  />
                  </div>
                )}

                {saveError && <p className="formError">{saveError}</p>}
              </div>

              {tab !== "layout" && (
                <PdfViewer url={previewUrl} loading={previewLoading}
                  scrollToPage={sectionPages[TAB_ANCHOR[tab]]} scrollNonce={scrollNonce}
                  onDownload={() => window.open(pdfUrl, "_blank", "noopener")} />
              )}
            </div>
          </>
        )}
      </StateView>
    </div>
  );
}
