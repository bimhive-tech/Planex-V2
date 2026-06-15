"use client";

// Create a company (shell-only: just a name; backend seeds its Company Admin role).
import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import type { CompanyRow } from "@/types/settings";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function CompanyFormModal({ open, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function close() {
    setName("");
    setError(null);
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post<CompanyRow>("/companies/", { name });
      onCreated();
      close();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create company.");
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="New company"
      onClose={close}
      footer={
        <>
          <Button variant="secondary" onClick={close} type="button">Cancel</Button>
          <Button type="submit" form="company-form" disabled={submitting}>
            {submitting ? "Creating…" : "Create company"}
          </Button>
        </>
      }
    >
      <form id="company-form" onSubmit={handleSubmit}>
        <Input
          label="Company name"
          name="name"
          required
          autoFocus
          placeholder="Acme Construction"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
