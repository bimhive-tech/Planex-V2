"use client";

// Create/rename a role. Permissions are set separately in the Permissions matrix,
// so this modal handles the name only.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import type { RoleRow } from "@/types/settings";
import { companyQuery } from "./companyQuery";

interface Props {
  open: boolean;
  companyId: string;
  role: RoleRow | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function RoleFormModal({ open, companyId, role, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(role?.name ?? "");
      setError(null);
    }
  }, [open, role]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (role) {
        await api.patch<RoleRow>(`/roles/${role.id}/${companyQuery(companyId)}`, { name });
      } else {
        await api.post<RoleRow>(`/roles/${companyQuery(companyId)}`, { name });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save role.");
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={role ? "Rename role" : "New role"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="role-form" disabled={submitting}>
            {submitting ? "Saving…" : role ? "Save" : "Create role"}
          </Button>
        </>
      }
    >
      <form id="role-form" onSubmit={handleSubmit}>
        <Input
          label="Role name"
          name="name"
          required
          autoFocus
          placeholder="Site Engineer"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <p className="formHint">Set this role’s permissions in the Permissions tab.</p>
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
