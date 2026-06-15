"use client";

// Settings → Info: full-width company profile — a summary strip + an editable
// details card.
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StateView } from "@/components/ui/StateView";
import { api, ApiError } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { formatDate } from "@/lib/format";
import type { CompanyInfo } from "@/types/settings";
import styles from "./InfoTab.module.css";

interface Form {
  name: string;
  phone_number: string;
  email: string;
  website: string;
  address: string;
}

const EMPTY: Form = { name: "", phone_number: "", email: "", website: "", address: "" };

export function InfoTab({ canEdit }: { canEdit: boolean }) {
  const { data, loading, error, reload } = useFetch(() => api.get<CompanyInfo>("/company/"), []);
  const [form, setForm] = useState<Form>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      setForm({
        name: data.name, phone_number: data.phone_number, email: data.email,
        website: data.website, address: data.address,
      });
    }
  }, [data]);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setSaved(false);
  };

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      await api.patch<CompanyInfo>("/company/", form);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save changes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <StateView loading={loading} error={error} isEmpty={false} onRetry={reload}>
      {data && (
        <div className={styles.wrap}>
          <section className={styles.summary}>
            <div className={styles.identity}>
              <span className={styles.avatar} aria-hidden="true">
                {data.name.slice(0, 1).toUpperCase()}
              </span>
              <div className={styles.identityText}>
                <span className={styles.companyName}>{data.name}</span>
                <span className={styles.slug}>{data.slug}</span>
              </div>
            </div>
            <div className={styles.summaryStats}>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Users</span>
                <span className={`${styles.statValue} tnum`}>{data.user_count}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Created</span>
                <span className={styles.statValue}>{formatDate(data.created_at)}</span>
              </div>
              <div className={styles.badges}>
                {data.is_platform_admin && <Badge tone="info">Platform</Badge>}
                <Badge tone={data.is_active ? "success" : "neutral"}>
                  {data.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>
            </div>
          </section>

          <form className={styles.card} onSubmit={handleSave}>
            <h2 className={styles.cardTitle}>Company details</h2>
            <div className={styles.grid}>
              <div className={styles.full}>
                <Input label="Company name" name="name" required value={form.name}
                  onChange={set("name")} disabled={!canEdit} />
              </div>
              <Input label="Phone" name="phone_number" value={form.phone_number}
                onChange={set("phone_number")} disabled={!canEdit} />
              <Input label="Email" name="email" type="email" value={form.email}
                onChange={set("email")} disabled={!canEdit} />
              <div className={styles.full}>
                <Input label="Website" name="website" value={form.website}
                  onChange={set("website")} disabled={!canEdit} />
              </div>
              <div className={`${styles.field} ${styles.full}`}>
                <label className={styles.label} htmlFor="address">Address</label>
                <textarea id="address" className={styles.textarea} rows={3}
                  value={form.address} onChange={set("address")} disabled={!canEdit} />
              </div>
            </div>

            {canEdit && (
              <div className={styles.actions}>
                {saveError && <span className={styles.error}>{saveError}</span>}
                {saved && <span className={styles.success}>Saved</span>}
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving…" : "Save changes"}
                </Button>
              </div>
            )}
          </form>
        </div>
      )}
    </StateView>
  );
}
