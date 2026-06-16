"use client";

// Template Builder — full control over a report's design. Loads the template,
// edits its config via the declarative schema, and saves back.
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
import styles from "./builder.module.css";

export function TemplateBuilder({ templateId }: { templateId: string }) {
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [config, setConfig] = useState<ReportConfig>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { loading, error, reload } = useFetch(async () => {
    const t = await api.get<ReportTemplate>(`/report-templates/${templateId}/`);
    setName(t.name);
    setIsDefault(t.is_default);
    setConfig(t.config);
    return t;
  }, [templateId]);

  function update(path: string, value: unknown) {
    setConfig((c) => setPath(c, path, value));
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

  return (
    <div className={styles.page}>
      <div className={styles.bar}>
        <Link href={ROUTES.reportTemplates} className={styles.back}>
          <Icon name="chevronDown" size={16} style={{ transform: "rotate(90deg)" }} />
          Templates
        </Link>
        <input
          className={styles.nameInput}
          value={name}
          onChange={(e) => { setName(e.target.value); setSaved(false); }}
          aria-label="Template name"
        />
        <div className={styles.barActions}>
          <label className={styles.defaultToggle}>
            <input type="checkbox" checked={isDefault} onChange={(e) => { setIsDefault(e.target.checked); setSaved(false); }} />
            Default
          </label>
          {saved && <span className={styles.saved}>Saved</span>}
          <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </div>
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView loading={loading} error={error} isEmpty={false} onRetry={reload}>
        {BUILDER_SECTIONS.map((section) => (
          <section key={section.title} className={styles.section}>
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>{section.title}</h2>
              {section.hint && <p className={styles.sectionHint}>{section.hint}</p>}
            </div>
            <div className={styles.fields}>
              {section.fields.map((field) => (
                <BuilderField
                  key={field.path}
                  field={field}
                  value={getPath(config, field.path)}
                  onChange={(v) => update(field.path, v)}
                />
              ))}
            </div>
          </section>
        ))}
      </StateView>
    </div>
  );
}
