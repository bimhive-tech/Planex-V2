"use client";

// Template Builder. Three top-level modes:
//   • Page Designer         — master page: paper, margins, header/footer bands.
//   • Report Configuration  — Canva-style drag/drop/resize page layout.
//   • Content & Labels      — the per-section toggles and wording that drive
//     the generated PDF today; kept because the renderer still reads them.
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import { BUILDER_SECTIONS, getPath, setPath } from "@/lib/reportTemplate";
import { readPageDesign, readPages } from "@/lib/reportLayout";
import type { LayoutPage, PageDesign } from "@/lib/reportLayout";
import type { ReportConfig, ReportTemplate } from "@/types/report";
import { BuilderField } from "./BuilderField";
import { BuilderPreview } from "./BuilderPreview";
import { PageDesigner } from "./designer/PageDesigner";
import { ReportConfigurator } from "./designer/ReportConfigurator";
import styles from "./builder.module.css";

type Mode = "design" | "layout" | "content";

const MODES: { key: Mode; label: string }[] = [
  { key: "design", label: "Page Designer" },
  { key: "layout", label: "Report Configuration" },
  { key: "content", label: "Content & Labels" },
];

export function TemplateBuilder({ templateId }: { templateId: string }) {
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [config, setConfig] = useState<ReportConfig>({});
  const [mode, setMode] = useState<Mode>("design");
  const [activeKey, setActiveKey] = useState(BUILDER_SECTIONS[0].key);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

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

  // Both take updaters and re-read from the freshest config inside setConfig,
  // so two edits in one tick can't read the same stale snapshot and clobber
  // each other (a fast double-click on the palette did exactly that).
  function setDesign(updater: (prev: PageDesign) => PageDesign) {
    setConfig((current) => ({ ...current, page_design: updater(readPageDesign(current)) }));
    setSaved(false);
  }

  function setPages(updater: (prev: LayoutPage[]) => LayoutPage[]) {
    setConfig((current) => ({
      ...current,
      layout: { ...(current.layout as object), pages: updater(readPages(current)) },
    }));
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

  async function handleSeedLayout() {
    setSeeding(true);
    setActionError(null);
    try {
      const updated = await api.post<ReportTemplate>(`/report-templates/${templateId}/seed-layout/`);
      setConfig(updated.config);
      setMode("layout");
      setSaved(true); // the endpoint already persisted this layout server-side
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't build a starting layout.");
    } finally {
      setSeeding(false);
    }
  }

  const section = BUILDER_SECTIONS.find((s) => s.key === activeKey) ?? BUILDER_SECTIONS[0];
  const design = readPageDesign(config);
  const pages = readPages(config);
  const canvasIsEmpty = pages.every((p) => p.elements.length === 0 && !p.repeat);

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
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => { setIsDefault(e.target.checked); setSaved(false); }}
              />
              Default
            </label>
            <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
          </div>
        </div>
        <nav className={styles.tabs} aria-label="Builder mode">
          {MODES.map((m) => (
            <button
              key={m.key}
              className={`${styles.tab} ${m.key === mode ? styles.tabActive : ""}`}
              onClick={() => setMode(m.key)}
              type="button"
            >
              {m.label}
            </button>
          ))}
        </nav>
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView loading={loading} error={error} isEmpty={false} onRetry={reload}>
        {mode === "design" && <PageDesigner design={design} onChange={setDesign} />}

        {mode === "layout" && (
          <>
            {canvasIsEmpty && (
              <div className={styles.seedBanner}>
                <p>
                  This canvas is empty — the PDF still uses your Content & Labels sections below.
                  Start from a layout built from those sections instead of from scratch.
                </p>
                <Button onClick={handleSeedLayout} disabled={seeding} variant="secondary">
                  {seeding ? "Building…" : "Start from my current sections"}
                </Button>
              </div>
            )}
            <ReportConfigurator design={design} pages={pages} onChange={setPages} />
          </>
        )}

        {mode === "content" && (
          <div className={styles.workspace}>
            <aside className={styles.palette} aria-label="Report pages">
              <h2 className={styles.panelTitle}>Sections</h2>
              <p className={styles.panelHint}>Tick to include a section; click to edit it.</p>
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
                  {design.size} {design.orientation}
                </span>
              </div>
              <BuilderPreview config={config} pageKey={section.key} name={name} />
            </main>

            <aside className={styles.inspector} aria-label="Section properties">
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
        )}
      </StateView>
    </div>
  );
}
