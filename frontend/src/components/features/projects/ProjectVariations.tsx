"use client";

// Variations tab — Variation Orders. Two sub-tabs: Schedule (SVO, moves the
// finish date) and Cost (CVO, changes the contract value). Each is auto-numbered
// and goes Pending → Approved/Rejected; the effect applies only once approved.
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import styles from "./milestones.module.css";
import v from "./variations.module.css";

type Kind = "schedule" | "cost";
type Status = "pending" | "approved" | "rejected";

interface Variation {
  id: string;
  kind: Kind;
  number: string;
  title: string;
  reason: string;
  date: string | null;
  status: Status;
  status_display: string;
  decided_at: string | null;
  decided_by_name: string;
  previous_finish: string | null;
  new_finish: string | null;
  impact_days: number | null;
  amount: string;
}

const STATUS_TONE: Record<Status, "warning" | "success" | "danger"> = {
  pending: "warning", approved: "success", rejected: "danger",
};

export function ProjectVariations({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const [kind, setKind] = useState<Kind>("schedule");
  const { data, loading, error, reload } = useFetch(
    () => api.get<Variation[]>(`/projects/${projectId}/variations/?kind=${kind}`),
    [projectId, kind],
  );
  const [modal, setModal] = useState<{ variation: Variation | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];

  // Only APPROVED variations count toward the headline figures.
  const summary = useMemo(() => {
    const approved = items.filter((x) => x.status === "approved");
    const pending = items.filter((x) => x.status === "pending").length;
    if (kind === "schedule") {
      const finish = approved.find((x) => x.new_finish)?.new_finish ?? null; // list is date-desc
      const days = approved.reduce((a, x) => a + (x.impact_days ?? 0), 0);
      return { finish, days, pending };
    }
    const total = approved.reduce((a, x) => a + (Number(x.amount) || 0), 0);
    return { total, pending };
  }, [items, kind]);

  async function decide(x: Variation, decision: "approve" | "reject") {
    setActionError(null);
    try {
      await api.post(`/projects/${projectId}/variations/${x.id}/decision/`, { decision });
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update.");
    }
  }

  async function remove(x: Variation) {
    if (!window.confirm(`Delete ${x.number}?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/variations/${x.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Variations</h2>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />}
            onClick={() => setModal({ variation: null })}>
            New {kind === "schedule" ? "SVO" : "CVO"}
          </Button>
        )}
      </header>

      <div className={v.subtabs}>
        <button className={`${v.subtab} ${kind === "schedule" ? v.active : ""}`} onClick={() => setKind("schedule")}>
          Schedule (SVO)
        </button>
        <button className={`${v.subtab} ${kind === "cost" ? v.active : ""}`} onClick={() => setKind("cost")}>
          Cost (CVO)
        </button>
      </div>

      <div className={v.banner}>
        {kind === "schedule" ? (
          <>
            <span>Current revised finish: <strong>{summary.finish ? formatDate(summary.finish) : "—"}</strong></span>
            <span>Approved impact: <strong>{summary.days} day{summary.days === 1 ? "" : "s"}</strong></span>
          </>
        ) : (
          <span>Approved cost impact: <strong>{(summary.total ?? 0).toLocaleString()}</strong></span>
        )}
        {summary.pending > 0 && <span className={v.pendingNote}>{summary.pending} pending</span>}
      </div>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={items.length === 0}
        emptyTitle={kind === "schedule" ? "No schedule variations" : "No cost variations"}
        emptyText={canManage
          ? (kind === "schedule"
            ? "Raise an SVO to extend the finish date — it applies once approved."
            : "Raise a CVO to add or omit cost — it counts once approved.")
          : undefined}
        onRetry={reload}
      >
        <ul className={styles.list}>
          {items.map((x) => (
            <li key={x.id} className={styles.item}>
              <div className={styles.itemBody}>
                <span className={styles.itemTitle}>
                  <span className={v.num}>{x.number}</span> {x.title}{" "}
                  <Badge tone={STATUS_TONE[x.status]}>{x.status_display}</Badge>
                </span>
                <span className={styles.itemMeta}>
                  {x.kind === "schedule"
                    ? <>{x.previous_finish ? formatDate(x.previous_finish) : "—"} → {x.new_finish ? formatDate(x.new_finish) : "—"}
                        {x.impact_days != null && <> · {x.impact_days > 0 ? "+" : ""}{x.impact_days} day{Math.abs(x.impact_days) === 1 ? "" : "s"}</>}</>
                    : <span className={Number(x.amount) < 0 ? v.neg : v.pos}>
                        {Number(x.amount) < 0 ? "" : "+"}{Number(x.amount).toLocaleString()}
                      </span>}
                  {x.date ? ` · raised ${formatDate(x.date)}` : ""}
                  {x.decided_at ? ` · ${x.status_display.toLowerCase()} ${formatDate(x.decided_at)}` : ""}
                </span>
                {x.reason && <span className={v.reason}>{x.reason}</span>}
              </div>
              {canManage && (
                <div className={styles.itemActions}>
                  {x.status === "pending" && (
                    <>
                      <Button size="sm" onClick={() => decide(x, "approve")}>Approve</Button>
                      <Button size="sm" variant="secondary" onClick={() => decide(x, "reject")}>Reject</Button>
                    </>
                  )}
                  <button className={styles.iconBtn} aria-label="Edit" onClick={() => setModal({ variation: x })}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button className={styles.iconBtn} aria-label="Delete" onClick={() => remove(x)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </StateView>

      {modal && (
        <VariationModal projectId={projectId} variation={modal.variation} defaultKind={kind}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}

function VariationModal({ projectId, variation, defaultKind, onClose, onSaved }: {
  projectId: string; variation: Variation | null; defaultKind: Kind;
  onClose: () => void; onSaved: () => void;
}) {
  const isEdit = !!variation;
  const kind = variation?.kind ?? defaultKind;
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const [newFinish, setNewFinish] = useState("");
  const [amount, setAmount] = useState("0");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(variation?.title ?? "");
    setDate(variation?.date ?? "");
    setReason(variation?.reason ?? "");
    setNewFinish(variation?.new_finish ?? "");
    setAmount(variation?.amount ?? "0");
  }, [variation]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const body = kind === "schedule"
      ? { kind, title, date: date || null, reason, new_finish: newFinish || null }
      : { kind, title, date: date || null, reason, amount: Number(amount) || 0 };
    try {
      if (isEdit && variation) await api.patch(`/projects/${projectId}/variations/${variation.id}/`, body);
      else await api.post(`/projects/${projectId}/variations/`, body);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  const label = kind === "schedule" ? "schedule variation (SVO)" : "cost variation (CVO)";
  return (
    <Modal open title={`${isEdit ? "Edit" : "New"} ${label}`} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="variation-form" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
        </>
      }>
      <form id="variation-form" onSubmit={submit} className={styles.form}>
        <Input label="Title" name="title" required autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
        {kind === "schedule"
          ? <Input label="New finish date" name="new_finish" type="date" required value={newFinish} onChange={(e) => setNewFinish(e.target.value)} />
          : <Input label="Amount (− to omit)" name="amount" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />}
        <Input label="Date raised (optional)" name="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <label className={v.reasonField}>
          <span>Reason (optional)</span>
          <textarea className={v.reasonInput} rows={3} value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. payment delay, added scope…" />
        </label>
        <p className={v.hint}>The VO number is assigned automatically. It stays Pending until you approve or reject it.</p>
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
