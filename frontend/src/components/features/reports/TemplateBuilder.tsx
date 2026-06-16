"use client";

// Template Builder: page-type tabs (Cover, TOC, Project Info, Description,
// Progress Report, Progress Images, Attachments, Design). The left "Pages" list
// shows/hides pages, the centre shows a live preview, and the right inspector
// edits the active page's real properties — every change feeds the PDF.
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import { BUILDER_SECTIONS, getPath, setPath } from "@/lib/reportTemplate";
import type { ReportConfig, ReportTemplate } from "@/types/report";
import { BuilderField } from "./BuilderField";
import { BuilderPreview } from "./BuilderPreview";
import styles from "./builder.module.css";

export function TemplateBuilder({ templateId }: { templateId: string }) {
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [config, setConfig] = useState<ReportConfig>({});
  const [activeKey, setActiveKey] = useState(BUILDER_SECTIONS[0].key);
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

  const section = BUILDER_SECTIONS.find((s) => s.key === activeKey) ?? BUILDER_SECTIONS[0];

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
              onChange={(e) => { setName(e.target.value); setSaved(false); }}
              aria-label="Template name"
            />
            <span className={saved ? styles.saved : styles.unsaved}>
              {saved ? "All changes saved" : "Unsaved changes"}
            </span>
          </div>
          <div className={styles.barActions}>
            <label className={styles.defaultToggle}>
              <input type="checkbox" checked={isDefault} onChange={(e) => { setIsDefault(e.target.checked); setSaved(false); }} />
              Default
            </label>
            <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
          </div>
        </div>
        <nav className={styles.tabs} aria-label="Report pages">
          {BUILDER_SECTIONS.map((s) => (
            <button
              key={s.key}
              className={`${styles.tab} ${s.key === activeKey ? styles.tabActive : ""}`}
              onClick={() => setActiveKey(s.key)}
              type="button"
            >
              {s.title}
            </button>
          ))}
        </nav>
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView loading={loading} error={error} isEmpty={false} onRetry={reload}>
        <div className={styles.workspace}>
          <aside className={styles.palette} aria-label="Report pages">
            <h2 className={styles.panelTitle}>Pages</h2>
            <p className={styles.panelHint}>Tick to include a page; click to edit it.</p>
            <div className={styles.pageList}>
              {BUILDER_SECTIONS.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  className={`${styles.pageRow} ${s.key === activeKey ? styles.pageRowActive : ""}`}
                  onClick={() => setActiveKey(s.key)}
                >
                  {s.enablePath ? (
                    <input
                      type="checkbox"
                      checked={Boolean(getPath(config, s.enablePath))}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => update(s.enablePath as string, e.target.checked)}
                      aria-label={`Include ${s.title}`}
                    />
                  ) : (
                    <Icon name="settings" size={14} />
                  )}
                  <span className={styles.pageRowLabel}>{s.title}</span>
                </button>
              ))}
            </div>
          </aside>

          <main className={styles.canvasArea}>
            <div className={styles.canvasTools}>
              <span className={styles.paperSelect}>{section.title}</span>
              <span className={styles.paperSelect}>
                {String(getPath(config, "page.size") ?? "A4")} {String(getPath(config, "page.orientation") ?? "portrait")}
              </span>
            </div>
            <BuilderPreview config={config} pageKey={section.key} name={name} />
          </main>

          <aside className={styles.inspector} aria-label="Page properties">
            <div className={styles.sectionHead}>
              <h3 className={styles.sectionTitle}>{section.title}</h3>
              {section.hint && <p className={styles.sectionHint}>{section.hint}</p>}
            </div>
            <div className={styles.fields}>
              {section.enablePath && (
                <BuilderField
                  field={{ path: section.enablePath, label: `Show ${section.title} page`, type: "toggle" }}
                  value={getPath(config, section.enablePath)}
                  onChange={(value) => update(section.enablePath as string, value)}
                />
              )}
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
