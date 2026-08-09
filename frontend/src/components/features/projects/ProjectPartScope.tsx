"use client";

// Part (Contracted Sub-Scope) tab — some contracts track a specific "Part" of
// the work (its own amount/baseline/forecast/delay) alongside the whole
// project. Its own tab rather than buried in the edit-project drawer, since
// it's a distinct thing being tracked, not general project metadata.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ProjectDetail } from "@/types/project";
import formStyles from "./projectForm.module.css";
import styles from "./milestones.module.css";

const FIELDS = ["part_amount", "part_completion_revised", "part_forecast_completion", "part_delay_days"] as const;
type Form = Record<(typeof FIELDS)[number], string>;

const blank = (p: ProjectDetail): Form => ({
  part_amount: p.part_amount ?? "",
  part_completion_revised: p.part_completion_revised ?? "",
  part_forecast_completion: p.part_forecast_completion ?? "",
  part_delay_days: p.part_delay_days === null ? "" : String(p.part_delay_days),
});

export function ProjectPartScope({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data: project, loading, error, reload } = useFetch(
    () => api.get<ProjectDetail>(`/projects/${projectId}/`),
    [projectId],
  );
  const [form, setForm] = useState<Form | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (project) setForm(blank(project));
  }, [project]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setSaved(false);
    setForm((f) => (f ? { ...f, [k]: e.target.value } : f));
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSubmitting(true);
    setSaveError(null);
    const payload: Record<string, unknown> = { ...form };
    for (const k of FIELDS) if (!payload[k]) payload[k] = null;
    try {
      await api.patch<ProjectDetail>(`/projects/${projectId}/`, payload);
      setSaved(true);
      reload();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Part (Contracted Sub-Scope)</h2>
      </header>

      <StateView loading={loading || !form} error={error} isEmpty={false} onRetry={reload}>
        {form && (
          <form onSubmit={submit} className={formStyles.form}>
            <p className={formStyles.sectionHint}>
              Only fill these in if this contract tracks a specific &quot;Part&quot; of the work alongside the whole
              project — its own amount, baseline, forecast, and delay, tracked in parallel with the project-wide
              figures shown elsewhere.
            </p>
            <Input
              label="Part amount" name="part_amount" type="number" step="0.01"
              value={form.part_amount} onChange={set("part_amount")} disabled={!canManage}
            />
            <div className={formStyles.row2}>
              <Input
                label="Completion (revised baseline)" name="part_completion_revised" type="date"
                value={form.part_completion_revised} onChange={set("part_completion_revised")} disabled={!canManage}
              />
              <Input
                label="Forecasted completion" name="part_forecast_completion" type="date"
                value={form.part_forecast_completion} onChange={set("part_forecast_completion")} disabled={!canManage}
              />
            </div>
            <Input
              label="Delay (calendar days)" name="part_delay_days" type="number" step="1"
              value={form.part_delay_days} onChange={set("part_delay_days")} disabled={!canManage}
            />
            {saveError && <p className="formError">{saveError}</p>}
            {canManage && (
              <div>
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Saving…" : saved ? "Saved" : "Save"}
                </Button>
              </div>
            )}
          </form>
        )}
      </StateView>
    </section>
  );
}
