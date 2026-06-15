"use client";

// Create/edit a user. Platform admins pick the user's company on create (searchable
// dropdown); company admins always create within their own company. Roles use a
// searchable multi-select. Edit allows changing everything, including email/password.
import { useEffect, useMemo, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { SearchSelect } from "@/components/ui/SearchSelect";
import { api, ApiError, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { CompanyRow, RoleRow, UserRow } from "@/types/settings";
import { companyQuery } from "./companyQuery";
import styles from "./userForm.module.css";

interface Props {
  open: boolean;
  contextCompanyId: string; // the company the Users tab is currently viewing
  isPlatformAdmin: boolean;
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

export function UserFormModal({ open, contextCompanyId, isPlatformAdmin, user, onClose, onSaved }: Props) {
  const isEdit = !!user;
  const [companyId, setCompanyId] = useState(contextCompanyId);
  const [form, setForm] = useState<Form>(EMPTY);
  const [roleIds, setRoleIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Company options (platform admin, create mode only).
  const showCompanyPicker = isPlatformAdmin && !isEdit;
  const { data: companyData } = useFetch(
    () => (showCompanyPicker
      ? api.get<Paginated<CompanyRow>>("/companies/?page_size=100")
      : Promise.resolve(null)),
    [showCompanyPicker, open],
  );

  // Roles for the chosen company.
  const { data: roleData } = useFetch(
    () => api.get<Paginated<RoleRow>>(`/roles/${companyQuery(companyId, { page_size: "100" })}`),
    [companyId, open],
  );
  const roleOptions = useMemo(
    () => (roleData?.results ?? []).map((r) => ({ value: r.id, label: r.name })),
    [roleData],
  );
  const companyOptions = useMemo(
    () => (companyData?.results ?? []).map((c) => ({ value: c.id, label: c.name })),
    [companyData],
  );

  useEffect(() => {
    if (open) {
      setCompanyId(contextCompanyId);
      setForm(user
        ? { ...EMPTY, email: user.email, first_name: user.first_name, last_name: user.last_name,
            phone_number: user.phone_number, is_active: user.is_active }
        : EMPTY);
      setRoleIds(user?.role_ids ?? []);
      setError(null);
    }
  }, [open, user, contextCompanyId]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  function changeCompany(ids: string[]) {
    setCompanyId(ids[0] ?? contextCompanyId);
    setRoleIds([]); // roles are company-specific
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (isEdit && user) {
        const body: Record<string, unknown> = {
          email: form.email,
          first_name: form.first_name,
          last_name: form.last_name,
          phone_number: form.phone_number,
          is_active: form.is_active,
          role_ids: roleIds,
        };
        if (form.password) body.password = form.password; // blank = unchanged
        await api.patch<UserRow>(`/users/${user.id}/${companyQuery(companyId)}`, body);
      } else {
        await api.post<UserRow>(`/users/${companyQuery(companyId)}`, {
          email: form.email,
          password: form.password,
          first_name: form.first_name,
          last_name: form.last_name,
          phone_number: form.phone_number,
          role_ids: roleIds,
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
        {showCompanyPicker && (
          <SearchSelect
            label="Company"
            placeholder="Select a company"
            options={companyOptions}
            value={[companyId]}
            onChange={changeCompany}
          />
        )}

        <Input label="Email" name="email" type="email" required
          placeholder="person@company.com" value={form.email} onChange={set("email")} />
        <Input label={isEdit ? "New password (leave blank to keep)" : "Password"} name="password"
          type="password" required={!isEdit} placeholder="At least 8 characters"
          value={form.password} onChange={set("password")} />

        <div className={styles.row2}>
          <Input label="First name" name="first_name" value={form.first_name} onChange={set("first_name")} />
          <Input label="Last name" name="last_name" value={form.last_name} onChange={set("last_name")} />
        </div>
        <Input label="Phone" name="phone_number" value={form.phone_number} onChange={set("phone_number")} />

        <SearchSelect
          label="Roles"
          placeholder="Assign roles"
          options={roleOptions}
          value={roleIds}
          onChange={setRoleIds}
          multiple
        />

        {isEdit && (
          <label className={styles.activeRow}>
            <input type="checkbox" checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
            <span>Active <span className={styles.hint}>— inactive users can’t sign in.</span></span>
          </label>
        )}

        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
