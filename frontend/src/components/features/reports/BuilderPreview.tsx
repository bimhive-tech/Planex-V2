"use client";

// Live A4 preview for the Template Builder. Renders a representation of the
// active page type, bound to the template config so edits show immediately.
import { type CSSProperties } from "react";

import { getPath } from "@/lib/reportTemplate";
import type { ReportConfig } from "@/types/report";
import styles from "./builder.module.css";

const isArabic = (s: string) => /[؀-ۿ]/.test(s);

export function BuilderPreview({ config, pageKey, name }: { config: ReportConfig; pageKey: string; name: string }) {
  const g = (path: string, fallback = "") => String(getPath(config, path) ?? fallback);
  const on = (path: string) => Boolean(getPath(config, path));

  const vars = {
    "--preview-heading": g("colors.section_heading", g("colors.heading", "#1F4E79")),
    "--preview-table": g("colors.table_header_bg", "#1F4E79"),
    "--pv-accent": g("colors.cover_accent", "#963634"),
    "--pv-cover-bg": g("colors.cover_bg", "#ffffff"),
    "--pv-toc": g("colors.toc_title", "#2E74B5"),
    "--pv-planned": g("colors.chart_planned", "#2E74B5"),
    "--pv-actual": g("colors.chart_actual", "#C0504D"),
    "--pv-rowalt": g("colors.table_row_alt", "#eef3f8"),
  } as CSSProperties;

  const dir = isArabic(g("cover.title") + g("labels.summary") + g("labels.project_info")) ? "rtl" : "ltr";

  return (
    <section className={styles.paper} style={vars} dir={dir} aria-label="Report preview">
      {pageKey === "cover" && <CoverPage g={g} on={on} />}
      {pageKey === "toc" && <TocPage g={g} on={on} />}
      {pageKey === "project_info" && <InfoPage g={g} />}
      {pageKey === "description" && <DescriptionPage g={g} />}
      {pageKey === "progress" && <ProgressPage g={g} on={on} />}
      {pageKey === "photos" && <PhotosPage g={g} />}
      {pageKey === "attachments" && <AttachmentsPage g={g} />}
      {pageKey === "design" && <DesignPage g={g} />}
    </section>
  );
}

type G = (path: string, fallback?: string) => string;
type On = (path: string) => boolean;

function CoverPage({ g, on }: { g: G; on: On }) {
  return (
    <div className={styles.coverPreview}>
      <div className={styles.coverAccent} />
      <div className={styles.coverBlock}>
        <div className={styles.coverReportTitle}>{g("cover.title", "Monthly Report")}</div>
        <div className={styles.coverMeta}>No. 52 · April 2026</div>
        {g("cover.prepared_by") && <div className={styles.coverMuted}>{g("cover.prepared_by")}</div>}
        {g("cover.org") && <div className={styles.coverOrg}>{g("cover.org")}</div>}
      </div>
      <div className={styles.coverProject}>{"{{Project Name}}"}</div>
      {on("cover.show_overall") && <div className={styles.coverOverall}>88%</div>}
    </div>
  );
}

function TocPage({ g, on }: { g: G; on: On }) {
  const entries = [
    ["sections.summary", g("labels.summary", "Summary")],
    ["sections.project_info", g("labels.project_info", "Project Information")],
    ["sections.description", g("labels.description", "Description")],
    ["sections.progress_overview", g("labels.progress_overview", "Progress")],
    ["sections.photos", g("labels.photos", "Photos")],
    ["sections.attachments", g("labels.attachments", "Attachments")],
  ].filter(([p]) => on(p));
  return (
    <div>
      <h2 className={styles.tocTitle}>{g("toc.title", "Contents")}</h2>
      {entries.map(([, label], i) => (
        <div className={styles.tocRow} key={label}>
          <span>{label}</span>
          <span className={styles.tocDots} />
          <span>{i + 2}</span>
        </div>
      ))}
    </div>
  );
}

function InfoPage({ g }: { g: G }) {
  const rows: [string, string][] = [
    [g("labels.info_name", "Project name"), "{{name}}"],
    [g("labels.info_client", "Client"), "{{client}}"],
    [g("labels.info_consultant", "Consultant"), "{{consultant}}"],
    [g("labels.info_contractor", "Contractor"), "{{contractor}}"],
    [g("labels.info_budget", "Value"), "{{budget}}"],
    [g("labels.info_finish", "Finish"), "{{date}}"],
  ];
  return (
    <div>
      <h2 className={styles.previewTitle}>{g("labels.project_info", "Project Information")}</h2>
      <dl className={styles.infoGrid}>
        {rows.map(([k, v]) => (
          <div key={k} className={styles.infoPair}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function DescriptionPage({ g }: { g: G }) {
  return (
    <div>
      <h2 className={styles.previewTitle}>{g("labels.description", "Project Description")}</h2>
      <ul className={styles.bullets}>
        <li>{"{{description line 1}}"}</li>
        <li>{"{{description line 2}}"}</li>
        <li>{"{{description line 3}}"}</li>
      </ul>
    </div>
  );
}

function ProgressPage({ g, on }: { g: G; on: On }) {
  return (
    <div>
      {on("sections.summary") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.summary", "Summary")}</h2>
          <table className={styles.previewTable}>
            <thead><tr><th>{g("labels.completed", "Completed")}</th><th>{g("labels.in_progress", "In Progress")}</th><th>{g("labels.not_started", "Not Started")}</th></tr></thead>
            <tbody><tr><td>300</td><td>140</td><td>29</td></tr></tbody>
          </table>
        </>
      )}
      {on("sections.progress_chart") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.progress_chart", "Planned vs Actual")}</h2>
          <div className={styles.chartRow}>
            <span className={`${styles.bar} ${styles.barPlanned}`} />
            <span className={`${styles.bar} ${styles.barActual}`} />
            <span className={`${styles.bar} ${styles.barPlanned}`} />
            <span className={`${styles.bar} ${styles.barActual}`} />
          </div>
        </>
      )}
      {on("sections.zone_progress") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.zone_progress", "Progress by Zone")}</h2>
          <table className={styles.previewTable}>
            <thead><tr><th>{g("labels.col_zone", "Zone")}</th><th>{g("labels.col_progress", "Progress")}</th></tr></thead>
            <tbody>
              <tr><td>{"{{zone}}"}</td><td>92%</td></tr>
              <tr className={styles.zebra}><td>{"{{zone}}"}</td><td>76%</td></tr>
            </tbody>
          </table>
        </>
      )}
      {on("sections.hierarchy_progress") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.hierarchy_progress", "تفصيل نسب الإنجاز")}</h2>
          <table className={styles.previewTable}>
            <thead><tr><th>{g("labels.col_zone", "Zone")}</th><th>{g("labels.col_actual", "Actual %")}</th><th>{g("labels.col_previous", "Previous %")}</th><th>{g("labels.col_planned", "Planned %")}</th></tr></thead>
            <tbody>
              <tr><td>{"{{zone}}"}</td><td>92%</td><td>88%</td><td>100%</td></tr>
              <tr className={styles.zebra}><td>{"  {{subzone}}"}</td><td>90%</td><td>85%</td><td>100%</td></tr>
            </tbody>
          </table>
        </>
      )}
      {on("sections.discipline_progress") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.discipline_progress", "الإنجاز حسب التخصص")}</h2>
          <table className={styles.previewTable}>
            <thead><tr><th>{g("labels.col_unit", "الوحدة")}</th><th>{g("labels.col_concrete", "الخرسانة")}</th><th>{g("labels.col_architecture", "المعماري")}</th><th>{g("labels.col_electrical", "الكهرباء")}</th><th>{g("labels.col_mechanical", "الميكانيكا")}</th></tr></thead>
            <tbody>
              <tr><td>{"{{unit}}"}</td><td>100%</td><td>96%</td><td>88%</td><td>81%</td></tr>
            </tbody>
          </table>
        </>
      )}
      {on("sections.area_dashboards") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.area_dashboards", "لوحات معلومات المناطق")}</h2>
          <div className={styles.chartRow}>
            <span className={`${styles.bar} ${styles.barPlanned}`} />
            <span className={`${styles.bar} ${styles.barActual}`} />
            <span className={`${styles.bar} ${styles.barPlanned}`} />
            <span className={`${styles.bar} ${styles.barActual}`} />
          </div>
          <div className={styles.photoGrid}>
            {[0, 1].map((i) => <div key={i} className={styles.photoCell}>Photo {i + 1}</div>)}
          </div>
        </>
      )}
      {on("sections.gantt_schedule") && (
        <>
          <h2 className={styles.previewTitle}>{g("labels.gantt_schedule", "الجدول الزمني للمشروع")}</h2>
          {[
            ["{{Zone A}}", "70%"],
            ["{{Building 1}}", "45%"],
            ["{{Building 2}}", "20%"],
          ].map(([label, pct]) => (
            <div className={styles.ganttRow} key={label}>
              <span className={styles.ganttLabel}>{label}</span>
              <span className={styles.ganttTrack}>
                <span className={styles.ganttFill} style={{ ["--gantt-fill" as string]: pct }} />
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function PhotosPage({ g }: { g: G }) {
  return (
    <div>
      <h2 className={styles.previewTitle}>{g("labels.photos", "Site Photos")}</h2>
      <div className={styles.photoGrid}>
        {[0, 1, 2, 3].map((i) => <div key={i} className={styles.photoCell}>Photo {i + 1}</div>)}
      </div>
    </div>
  );
}

function AttachmentsPage({ g }: { g: G }) {
  return (
    <div>
      <h2 className={styles.previewTitle}>{g("labels.attachments", "Attachments")}</h2>
      <div className={styles.attachPage}>1 attachment / page</div>
    </div>
  );
}

function DesignPage({ g }: { g: G }) {
  return (
    <div>
      <h2 className={styles.previewTitle}>{g("labels.project_info", "Sample heading")}</h2>
      <table className={styles.previewTable}>
        <thead><tr><th>Column</th><th>Column</th></tr></thead>
        <tbody>
          <tr><td>Row</td><td>Value</td></tr>
          <tr className={styles.zebra}><td>Row</td><td>Value</td></tr>
        </tbody>
      </table>
      <p className={styles.designNote}>Colors, fonts, header, footer, and tables apply to every page.</p>
    </div>
  );
}
