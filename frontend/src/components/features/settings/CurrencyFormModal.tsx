"use client";

// Create/edit a currency (Settings -> Master Data). is_default is set via its
// own "Set default" action in CurrencyList, not editable here.
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import type { CurrencyRow } from "@/types/settings";
import { companyQuery } from "./companyQuery";

interface Props {
  open: boolean;
  companyId: string;
  currency: CurrencyRow | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function CurrencyFormModal({ open, companyId, currency, onClose, onSaved }: Props) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setCode(currency?.code ?? "");
      setName(currency?.name ?? "");
      setSymbol(currency?.symbol ?? "");
      setError(null);
    }
  }, [open, currency]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (currency) {
        await api.patch(`/currencies/${currency.id}/${companyQuery(companyId)}`, { code, name, symbol });
      } else {
        await api.post(`/currencies/${companyQuery(companyId)}`, { code, name, symbol });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this currency.");
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={currency ? "Edit currency" : "New currency"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="currency-form" disabled={submitting}>
            {submitting ? "Saving…" : currency ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <form id="currency-form" onSubmit={handleSubmit}>
        <Input
          label="Code" name="code" required autoFocus maxLength={8}
          placeholder="AED" value={code} onChange={(e) => setCode(e.target.value)}
        />
        <Input
          label="Name" name="name" required
          placeholder="UAE Dirham" value={name} onChange={(e) => setName(e.target.value)}
        />
        <Input
          label="Symbol (optional)" name="symbol" maxLength={8}
          placeholder="$" value={symbol} onChange={(e) => setSymbol(e.target.value)}
        />
        {error && <p className="formError">{error}</p>}
      </form>
    </Modal>
  );
}
