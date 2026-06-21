"use client";

// Progress photo history for a scope (zone / subzone / phase): every photo
// recorded under its subtree, filterable by date range and — client-side, from
// what's present — subzone, phase, and activity. Shows who uploaded each photo,
// its date and caption; delete is gated by DELETE_PROGRESS_IMAGES.
import { useMemo, useState } from "react";
import Image from "next/image";

import { Modal } from "@/components/ui/Modal";
import { Icon } from "@/components/ui/Icon";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { ProgressImage } from "@/types/project";
import styles from "./progressGallery.module.css";

interface Props {
  projectId: string;
  scope: { id: string; name: string };
  canDelete: boolean;
  onClose: () => void;
}

const ALL = "__all__";

export function ProgressGalleryModal({ projectId, scope, canDelete, onClose }: Props) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [subzone, setSubzone] = useState(ALL);
  const [phase, setPhase] = useState(ALL);
  const [activity, setActivity] = useState(ALL);
  const [actionError, setActionError] = useState<string | null>(null);

  const qs = new URLSearchParams({ scope: scope.id });
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);

  const { data, loading, error, reload } = useFetch(
    () => api.get<ProgressImage[]>(`/projects/${projectId}/progress-images/?${qs.toString()}`),
    [projectId, scope.id, dateFrom, dateTo],
  );
  const images = useMemo(() => data ?? [], [data]);

  // Filter dropdown options come from what's actually present in the results.
  const subzones = useMemo(() => uniq(images.map((i) => i.subzone_code)), [images]);
  const phases = useMemo(() => uniq(images.map((i) => i.phase_name)), [images]);
  const activities = useMemo(() => uniq(images.map((i) => i.activity_name)), [images]);

  const shown = images.filter((i) =>
    (subzone === ALL || i.subzone_code === subzone) &&
    (phase === ALL || i.phase_name === phase) &&
    (activity === ALL || i.activity_name === activity));

  async function remove(img: ProgressImage) {
    if (!window.confirm("Delete this photo? This can't be undone.")) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/progress-images/${img.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete photo.");
    }
  }

  return (
    <Modal open title={`Photos · ${scope.name}`} onClose={onClose}>
      <div className={styles.filters}>
        <label className={styles.dateField}>
          <span>From</span>
          <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className={styles.dateField}>
          <span>To</span>
          <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        {subzones.length > 1 && (
          <Filter label="Subzone" value={subzone} onChange={setSubzone} options={subzones} />
        )}
        {phases.length > 1 && (
          <Filter label="Phase" value={phase} onChange={setPhase} options={phases} />
        )}
        {activities.length > 1 && (
          <Filter label="Activity" value={activity} onChange={setActivity} options={activities} />
        )}
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading}
        error={error}
        isEmpty={shown.length === 0}
        emptyTitle="No photos"
        emptyText="No progress photos match these filters."
        onRetry={reload}
      >
        <div className={styles.grid}>
          {shown.map((img) => (
            <figure className={styles.card} key={img.id}>
              <div className={styles.thumbWrap}>
                <Image className={styles.thumb} src={img.url} alt={img.caption || img.activity_name}
                  width={240} height={160} unoptimized />
                {canDelete && (
                  <button className={styles.delete} type="button" aria-label="Delete photo" onClick={() => remove(img)}>
                    <Icon name="trash" size={14} />
                  </button>
                )}
              </div>
              <figcaption className={styles.meta}>
                {img.caption && <span className={styles.caption}>{img.caption}</span>}
                <span className={styles.activity}>{img.activity_name}</span>
                <span className={styles.sub}>
                  {[img.subzone_code, img.phase_name].filter(Boolean).join(" · ")}
                </span>
                <span className={styles.byline}>
                  {img.date}{img.uploaded_by_name ? ` · ${img.uploaded_by_name}` : ""}
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      </StateView>
    </Modal>
  );
}

function Filter({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: string[];
}) {
  return (
    <label className={styles.selectField}>
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value={ALL}>All</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

const uniq = (xs: string[]) => Array.from(new Set(xs.filter(Boolean))).sort();
