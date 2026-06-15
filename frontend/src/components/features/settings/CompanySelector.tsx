"use client";

// Company switcher shown to platform admins on the Users/Roles tabs so they can
// manage any company. Company admins never see this (locked to own company).
import { Select } from "@/components/ui/Select";
import { api, type Paginated } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { CompanyRow } from "@/types/settings";

interface Props {
  value: string;
  onChange: (companyId: string) => void;
}

export function CompanySelector({ value, onChange }: Props) {
  // Page size bumped so all companies fit one request (selector, not a table).
  const { data } = useFetch(
    () => api.get<Paginated<CompanyRow>>("/companies/?page_size=100"),
    [],
  );
  const options = (data?.results ?? []).map((c) => ({ value: c.id, label: c.name }));

  return (
    <Select
      aria-label="Company"
      options={options.length ? options : [{ value, label: "Loading…" }]}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
