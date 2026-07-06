"use client";

// Report builder: pick progress photos uploaded in the schedule tab (via
// progress updates / accepted submissions) to include in the report's Progress
// Images section. Backend returns them ordered by date, earliest first — the
// order they'll appear in the PDF.
import { useState } from "react";

import { StateView } from "@/components/ui/StateView";
import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import type { ReportProgressPhoto } from "@/types/report";
import styles from "./progressImagePicker.module.css";

export function ProgressImagePicker({ reportId, canManage, onChanged }: {
  reportId: string; canManage: boolean; onChanged: () => void;
}) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<ReportProgressPhoto[]>(`/reports/${reportId}/progress-images/`),
    [reportId],
  );
  const photos = data ?? [];
  // Selection is seeded from the server, then owned locally as the user toggles.
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const current = selected ?? new Set(photos.filter((p) => p.selected).map((p) => p.id));

  async function toggle(id: string) {
    if (!canManage) return;
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
    setSaving(true);
    setActionError(null);
    try {
      await api.put(`/reports/${reportId}/progress-images/`, { selected_ids: [...next] });
      onChanged();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't save selection.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.wrap}>
      <header className={styles.head}>
        <div>
          <h2 className={styles.title}>Progress photos from the schedule</h2>
          <p className={styles.hint}>
            Tick the photos to include — they appear in the report ordered by date, earliest first.
          </p>
        </div>
        <span className={styles.count}>
          {current.size} selected{saving && " · saving…"}
        </span>
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={photos.length === 0}
        emptyTitle="No progress photos yet"
        emptyText="Photos attached to progress updates in the Schedule tab will show up here."
        onRetry={reload}
      >
        <div className={styles.grid}>
          {photos.map((p) => {
            const on = current.has(p.id);
            return (
              <button
                key={p.id} type="button"
                className={`${styles.item} ${on ? styles.itemOn : ""}`}
                onClick={() => toggle(p.id)} disabled={!canManage}
                aria-pressed={on}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img className={styles.thumb} src={p.url} alt={p.caption || "Progress photo"} />
                <span className={styles.check} aria-hidden>
                  {on && <Icon name="check" size={13} />}
                </span>
                <span className={styles.meta}>
                  <span className={styles.date}>{p.date ? formatDate(p.date) : "—"}</span>
                  {p.caption && <span className={styles.caption}>{p.caption}</span>}
                </span>
              </button>
            );
          })}
        </div>
      </StateView>
    </section>
  );
}
