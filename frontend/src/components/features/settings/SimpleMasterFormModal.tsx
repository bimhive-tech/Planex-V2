"use client";

// Create/rename a name-only master-data row (Project Type or Priority — same
// shape, so one modal covers both via the `resource` prop).
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { companyQuery } from "./companyQuery";

interface Row {
  id: string;
  name: string;
}

interface Props {
  open: boolean;
  resource: "project-types" | "project-priorities";
  label: string; // "project type" | "priority" — for modal copy
  companyId: string;
  item: Row | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function SimpleMasterFormModal({ open, resource, label, companyId, item, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(item?.name ?? "");
      setError(null);
    }
  }, [open, item]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (item) {
        await api.patch<Row>(`/${resource}/${item.id}/${companyQuery(companyId)}`, { name });
      } else {
        await api.post<Row>(`/${resource}/${companyQuery(companyId)}`, { name });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Couldn't save this ${label}.`);
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={item ? `Rename ${label}` : `New ${label}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="simple-master-form" disabled={submitting}>
            {submitting ? "Saving…" : item ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <form id="simple-master-form" onSubmit={handleSubmit}>
        <Input
          label="Name"
          name="name"
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
