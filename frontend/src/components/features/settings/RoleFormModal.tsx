"use client";

// Create/edit a role: name + grouped permission checkboxes (catalog from backend,
// already filtered to what the target company may grant).
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Checkbox } from "@/components/ui/Checkbox";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { PermissionGroup, RoleRow } from "@/types/settings";
import { companyQuery } from "./companyQuery";
import styles from "./RoleFormModal.module.css";

interface Props {
  open: boolean;
  companyId: string;
  role: RoleRow | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function RoleFormModal({ open, companyId, role, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: catalog } = useFetch(
    () => api.get<{ groups: PermissionGroup[] }>(`/permissions/${companyQuery(companyId)}`),
    [companyId, open],
  );

  // Seed form when (re)opening.
  useEffect(() => {
    if (open) {
      setName(role?.name ?? "");
      setSelected(new Set(role?.permissions ?? []));
      setError(null);
    }
  }, [open, role]);

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const body = { name, permissions: [...selected] };
    try {
      if (role) {
        await api.patch<RoleRow>(`/roles/${role.id}/${companyQuery(companyId)}`, body);
      } else {
        await api.post<RoleRow>(`/roles/${companyQuery(companyId)}`, body);
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
      title={role ? "Edit role" : "New role"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="role-form" disabled={submitting}>
            {submitting ? "Saving…" : role ? "Save role" : "Create role"}
          </Button>
        </>
      }
    >
      <form id="role-form" onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Role name"
          name="name"
          required
          autoFocus
          placeholder="Site Engineer"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <div className={styles.permsHeader}>Permissions</div>
        {(catalog?.groups ?? []).map((group) => (
          <fieldset key={group.group} className={styles.group}>
            <legend className={styles.groupLabel}>{group.group}</legend>
            {group.permissions.map((p) => (
              <Checkbox
                key={p.key}
                name={p.key}
                label={p.label}
                checked={selected.has(p.key)}
                onChange={() => toggle(p.key)}
              />
            ))}
          </fieldset>
        ))}

        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
