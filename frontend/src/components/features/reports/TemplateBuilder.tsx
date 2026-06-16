"use client";

// Template Builder workspace: palette, document preview, and config inspector.
import Link from "next/link";
import { useState, type CSSProperties } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import { BUILDER_SECTIONS, getPath, setPath } from "@/lib/reportTemplate";
import type { ReportConfig, ReportTemplate } from "@/types/report";
import { BuilderField } from "./BuilderField";
import styles from "./builder.module.css";

const ELEMENTS = [
  { label: "Text", icon: "text" },
  { label: "Heading", icon: "heading" },
  { label: "Image", icon: "image" },
  { label: "Table", icon: "table" },
  { label: "Key-Value List", icon: "list" },
  { label: "Page Break", icon: "pageBreak" },
  { label: "Spacer", icon: "spacer" },
  { label: "Divider", icon: "divider" },
] as const;

export function TemplateBuilder({ templateId }: { templateId: string }) {
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [config, setConfig] = useState<ReportConfig>({});
  const [activeSection, setActiveSection] = useState(BUILDER_SECTIONS[0].title);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { loading, error, reload } = useFetch(async () => {
    const template = await api.get<ReportTemplate>(`/report-templates/${templateId}/`);
    setName(template.name);
    setIsDefault(template.is_default);
    setConfig(template.config);
    return template;
  }, [templateId]);

  function update(path: string, value: unknown) {
    setConfig((current) => setPath(current, path, value));
    setSaved(false);
  }

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setActionError(null);
    try {
      await api.patch(`/report-templates/${templateId}/`, { name, is_default: isDefault, config });
      setSaved(true);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't save template.");
    } finally {
      setSaving(false);
    }
  }

  function handlePreview() {
    window.open(ROUTES.reports, "_blank", "noopener");
  }

  const section = BUILDER_SECTIONS.find((item) => item.title === activeSection) ?? BUILDER_SECTIONS[0];
  const headingColor = String(getPath(config, "colors.section_heading") ?? getPath(config, "colors.heading") ?? "#534AB7");
  const tableColor = String(getPath(config, "colors.table_header_bg") ?? "#534AB7");
  const previewStyle = {
    "--preview-heading": headingColor,
    "--preview-table": tableColor,
  } as CSSProperties;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href={ROUTES.reportTemplates} className={styles.back}>
          <Icon name="chevronDown" size={16} className={styles.backIcon} />
          Back to Templates
        </Link>
        <div className={styles.titleRow}>
          <div className={styles.nameRow}>
            <input
              className={styles.nameInput}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setSaved(false);
              }}
              aria-label="Template name"
            />
            <span className={styles.badge}>Draft</span>
            <span className={saved ? styles.saved : styles.unsaved}>
              {saved ? "All changes saved" : "Unsaved changes"}
            </span>
          </div>
          <div className={styles.barActions}>
            <Button variant="secondary" leadingIcon={<Icon name="eye" size={16} />} onClick={handlePreview}>Preview</Button>
            <Button variant="secondary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save as Draft"}
            </Button>
            <Button onClick={handleSave} disabled={saving}>Publish</Button>
          </div>
        </div>
        <nav className={styles.tabs} aria-label="Template builder sections">
          {BUILDER_SECTIONS.slice(0, 4).map((item) => (
            <button
              key={item.title}
              className={`${styles.tab} ${item.title === activeSection ? styles.tabActive : ""}`}
              onClick={() => setActiveSection(item.title)}
              type="button"
            >
              {item.title === "Page" ? "Builder" : item.title}
            </button>
          ))}
        </nav>
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView loading={loading} error={error} isEmpty={false} onRetry={reload}>
        <div className={styles.workspace}>
          <aside className={styles.palette} aria-label="Report elements">
            <h2 className={styles.panelTitle}>Add Elements</h2>
            <p className={styles.panelHint}>Drag and drop elements to build your template.</p>
            <div className={styles.elementList}>
              {ELEMENTS.map((item) => (
                <button className={styles.elementBtn} type="button" key={item.label}>
                  <Icon name={item.icon} size={16} />
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          </aside>

          <main className={styles.canvasArea}>
            <div className={styles.canvasTools}>
              <div className={styles.toolGroup}>
                <button className={styles.toolBtn} type="button" title="Undo"><Icon name="undo" size={16} /></button>
                <button className={styles.toolBtn} type="button" title="Redo"><Icon name="redo" size={16} /></button>
                <button className={styles.toolBtn} type="button" title="Duplicate"><Icon name="copy" size={16} /></button>
                <button className={styles.toolBtn} type="button" title="Delete"><Icon name="trash" size={16} /></button>
              </div>
              <span className={styles.paperSelect}>A4 Portrait</span>
            </div>
            <section className={styles.paper} style={previewStyle} aria-label="Report preview">
              <div className={styles.logoRow}>
                <div className={styles.logoMark}>MCG</div>
                <div className={styles.logoMark}>SINAI</div>
              </div>
              <h2 className={styles.previewTitle}>{String(getPath(config, "cover.title") || name || "Monthly Progress Report")}</h2>
              <dl className={styles.infoGrid}>
                <dt>Project:</dt><dd>{"{{Project Name}}"}</dd>
                <dt>Report No.:</dt><dd>{"{{Report Number}}"}</dd>
                <dt>Reporting Period:</dt><dd>{"{{From Date}} - {{To Date}}"}</dd>
                <dt>Prepared By:</dt><dd>{"{{Prepared By}}"}</dd>
                <dt>Date:</dt><dd>{"{{Report Date}}"}</dd>
              </dl>
              <div className={styles.previewBlock}>
                <h3>1. {String(getPath(config, "labels.summary") || "Executive Summary")}</h3>
                <p>{"{{Executive Summary}}"}</p>
              </div>
              <div className={styles.previewBlock}>
                <h3>2. {String(getPath(config, "labels.progress_overview") || "Overall Progress")}</h3>
                <table className={styles.previewTable}>
                  <thead>
                    <tr><th>Work Package</th><th>Planned %</th><th>Actual %</th><th>Variance</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>{"{{Table}}"}</td><td>82%</td><td>78%</td><td>-4%</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
            <div className={styles.pageStepper}>
              <button className={styles.toolBtn} type="button" aria-label="Previous page">
                <Icon name="chevronDown" size={16} className={styles.prevIcon} />
              </button>
              <span>1 / 6</span>
              <button className={styles.toolBtn} type="button" aria-label="Next page">
                <Icon name="chevronDown" size={16} className={styles.nextIcon} />
              </button>
            </div>
          </main>

          <aside className={styles.inspector} aria-label="Element properties">
            <div className={styles.inspectorHead}>
              <h2 className={styles.panelTitle}>Element Properties</h2>
              <label className={styles.defaultToggle}>
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => {
                    setIsDefault(e.target.checked);
                    setSaved(false);
                  }}
                />
                Default
              </label>
            </div>
            <div className={styles.sectionPicker}>
              {BUILDER_SECTIONS.map((item) => (
                <button
                  key={item.title}
                  className={`${styles.pickerBtn} ${item.title === activeSection ? styles.pickerActive : ""}`}
                  onClick={() => setActiveSection(item.title)}
                  type="button"
                >
                  {item.title}
                </button>
              ))}
            </div>
            <div className={styles.sectionHead}>
              <h3 className={styles.sectionTitle}>{section.title}</h3>
              {section.hint && <p className={styles.sectionHint}>{section.hint}</p>}
            </div>
            <div className={styles.fields}>
              {section.fields.map((field) => (
                <BuilderField
                  key={field.path}
                  field={field}
                  value={getPath(config, field.path)}
                  onChange={(value) => update(field.path, value)}
                />
              ))}
            </div>
          </aside>
        </div>
      </StateView>
    </div>
  );
}
