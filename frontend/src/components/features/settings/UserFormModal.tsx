"use client";

// Create/edit a user within the (selected) company. Create takes email+password;
// edit changes profile, active state, and role assignment. Roles are checkboxes.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Checkbox } from "@/components/ui/Checkbox";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { RoleRow, UserRow } from "@/types/settings";
import { companyQuery } from "./companyQuery";
import styles from "./RoleFormModal.module.css";

interface Props {
  open: boolean;
  companyId: string;
  user: UserRow | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

interface Form {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  is_active: boolean;
}

const EMPTY: Form = {
  email: "", password: "", first_name: "", last_name: "", phone_number: "", is_active: true,
};

export function UserFormModal({ open, companyId, user, onClose, onSaved }: Props) {
  const isEdit = !!user;
  const [form, setForm] = useState<Form>(EMPTY);
  const [roleIds, setRoleIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: roleData } = useFetch(
    () => api.get<Paginated<RoleRow>>(`/roles/${companyQuery(companyId, { page_size: "100" })}`),
    [companyId, open],
  );
  const roles = roleData?.results ?? [];

  useEffect(() => {
    if (open) {
      setForm(user ? { ...EMPTY, email: user.email, first_name: user.first_name,
        last_name: user.last_name, phone_number: user.phone_number, is_active: user.is_active } : EMPTY);
      setRoleIds(new Set(user?.role_ids ?? []));
      setError(null);
    }
  }, [open, user]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const toggleRole = (id: string) =>
    setRoleIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (isEdit && user) {
        await api.patch<UserRow>(`/users/${user.id}/${companyQuery(companyId)}`, {
          first_name: form.first_name,
          last_name: form.last_name,
          phone_number: form.phone_number,
          is_active: form.is_active,
          role_ids: [...roleIds],
        });
      } else {
        await api.post<UserRow>(`/users/${companyQuery(companyId)}`, {
          email: form.email,
          password: form.password,
          first_name: form.first_name,
          last_name: form.last_name,
          phone_number: form.phone_number,
          role_ids: [...roleIds],
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save user.");
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={isEdit ? "Edit user" : "New user"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="user-form" disabled={submitting}>
            {submitting ? "Saving…" : isEdit ? "Save user" : "Create user"}
          </Button>
        </>
      }
    >
      <form id="user-form" onSubmit={handleSubmit} className={styles.form}>
        {!isEdit && (
          <>
            <Input label="Email" name="email" type="email" required autoFocus
              placeholder="person@company.com" value={form.email} onChange={set("email")} />
            <Input label="Password" name="password" type="password" required
              placeholder="At least 8 characters" value={form.password} onChange={set("password")} />
          </>
        )}
        <div className={styles.form}>
          <Input label="First name" name="first_name" value={form.first_name} onChange={set("first_name")} />
          <Input label="Last name" name="last_name" value={form.last_name} onChange={set("last_name")} />
        </div>
        <Input label="Phone" name="phone_number" value={form.phone_number} onChange={set("phone_number")} />

        <div className={styles.permsHeader}>Roles</div>
        <fieldset className={styles.group}>
          {roles.length === 0 && <span className={styles.groupLabel}>No roles in this company yet</span>}
          {roles.map((r) => (
            <Checkbox key={r.id} name={`role-${r.id}`} label={r.name}
              checked={roleIds.has(r.id)} onChange={() => toggleRole(r.id)} />
          ))}
        </fieldset>

        {isEdit && (
          <Checkbox name="is_active" label="Active"
            description="Inactive users can't sign in."
            checked={form.is_active}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
        )}

        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
