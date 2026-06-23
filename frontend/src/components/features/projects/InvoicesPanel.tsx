"use client";

// Invoices (مستخلصات): name/reason + value + optional scan. Pulled into the
// report's invoices section. Editing requires the manage-finances permission.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { API_BASE } from "@/lib/constants";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import styles from "./finances.module.css";

interface Invoice {
  id: string; name: string; value: string; date: string | null; sort_order: number; has_image: boolean;
}

export function InvoicesPanel({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, loading, error, reload } = useFetch(
    () => api.get<Invoice[]>(`/projects/${projectId}/invoices/`),
    [projectId],
  );
  const [modal, setModal] = useState<{ invoice: Invoice | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = data ?? [];
  const total = items.reduce((s, i) => s + (Number(i.value) || 0), 0);

  async function remove(inv: Invoice) {
    if (!window.confirm(`Delete “${inv.name}”?`)) return;
    setActionError(null);
    try {
      await api.del(`/projects/${projectId}/invoices/${inv.id}/`);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  }

  return (
    <section className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>Invoices</h2>
        {canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Icon name="plus" size={15} />} onClick={() => setModal({ invoice: null })}>
            Add
          </Button>
        )}
      </header>

      {actionError && <p className="formError">{actionError}</p>}

      <StateView
        loading={loading} error={error} isEmpty={items.length === 0}
        emptyTitle="No invoices yet"
        emptyText={canManage ? "Log invoices (value + reason, optional scan) — they appear in the report." : undefined}
        onRetry={reload}
      >
        <ul className={styles.list}>
          {items.map((inv) => (
            <li key={inv.id} className={styles.item}>
              <div className={styles.itemBody}>
                <span className={styles.itemTitle}>{inv.name}</span>
                <span className={styles.muted}>
                  {Number(inv.value).toLocaleString()}{inv.date ? ` · ${formatDate(inv.date)}` : ""}
                  {inv.has_image && (
                    <>
                      {" · "}
                      <a className={styles.link} href={`${API_BASE}/projects/${projectId}/invoices/${inv.id}/image/`} target="_blank" rel="noreferrer">
                        View scan
                      </a>
                    </>
                  )}
                </span>
              </div>
              {canManage && (
                <div className={styles.itemActions}>
                  <button className={styles.iconBtn} aria-label="Edit" onClick={() => setModal({ invoice: inv })}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button className={styles.iconBtn} aria-label="Delete" onClick={() => remove(inv)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
        {items.length > 0 && <p className={styles.totalLine}>Total: {total.toLocaleString()}</p>}
      </StateView>

      {modal && (
        <InvoiceModal projectId={projectId} invoice={modal.invoice}
          onClose={() => setModal(null)} onSaved={reload} />
      )}
    </section>
  );
}

function InvoiceModal({ projectId, invoice, onClose, onSaved }: {
  projectId: string; invoice: Invoice | null; onClose: () => void; onSaved: () => void;
}) {
  const isEdit = !!invoice;
  const [name, setName] = useState("");
  const [value, setValue] = useState("0");
  const [date, setDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(invoice?.name ?? "");
    setValue(String(invoice?.value ?? "0"));
    setDate(invoice?.date ?? "");
    setFile(null);
  }, [invoice]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData();
    form.append("name", name);
    form.append("value", String(Number(value) || 0));
    if (date) form.append("date", date);
    if (file) form.append("image", file);
    try {
      if (isEdit && invoice) await api.uploadApi(`/projects/${projectId}/invoices/${invoice.id}/`, form, "PATCH");
      else await api.uploadApi(`/projects/${projectId}/invoices/`, form);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save.");
      setSubmitting(false);
    }
  }

  return (
    <Modal open title={isEdit ? "Edit invoice" : "Add invoice"} onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="invoice-form" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
        </>
      }>
      <form id="invoice-form" onSubmit={submit} className={styles.form}>
        <Input label="Name / reason" name="name" required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        <Input label="Value" name="value" type="number" step="0.01" min="0" value={value} onChange={(e) => setValue(e.target.value)} />
        <Input label="Date" name="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <label className={styles.fileLabel}>
          <span>Scan / image (optional)</span>
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {isEdit && invoice?.has_image && !file && <p className={styles.muted}>A scan is already attached. Choosing a file replaces it.</p>}
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
