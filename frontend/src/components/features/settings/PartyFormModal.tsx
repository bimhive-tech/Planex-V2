"use client";

// Create/edit a consultant, contractor or sub-contractor (name + contacts).
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { companyQuery } from "./companyQuery";

export interface PartyRow {
  id: string;
  name: string;
  phone: string;
  email: string;
}

interface Props {
  open: boolean;
  resource: "consultants" | "contractors" | "subcontractors";
  label: string; // "consultant" | "contractor" | "sub-contractor" — modal copy
  companyId: string;
  item: PartyRow | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function PartyFormModal({ open, resource, label, companyId, item, onClose, onSaved }: Props) {
  const [form, setForm] = useState({ name: "", phone: "", email: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setForm({ name: item?.name ?? "", phone: item?.phone ?? "", email: item?.email ?? "" });
    setError(null);
  }, [open, item]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (item) {
        await api.patch(`/${resource}/${item.id}/${companyQuery(companyId)}`, form);
      } else {
        await api.post(`/${resource}/${companyQuery(companyId)}`, form);
      }
      onSaved();
      onClose();
    } catch (err) {
      // Covers the duplicate-name refusal, which names the clash.
      setError(err instanceof ApiError ? err.message : `Couldn't save this ${label}.`);
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={item ? `Edit ${label}` : `New ${label}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="party-form" disabled={submitting}>
            {submitting ? "Saving…" : item ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <form id="party-form" onSubmit={handleSubmit}>
        <Input label="Name" name="name" required autoFocus value={form.name} onChange={set("name")} />
        <Input label="Phone" name="phone" value={form.phone} onChange={set("phone")} />
        <Input label="Email" name="email" type="email" value={form.email} onChange={set("email")} />
        {item && (
          <p className="formHint">
            Renaming updates every project that currently uses “{item.name}”, so none of them lose it.
          </p>
        )}
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
