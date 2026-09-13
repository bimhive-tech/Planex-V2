"use client";

// Fetches the signed-in user's own company's Master Data lists (Settings ->
// Master Data), used to populate the project form's dropdowns. No company
// param: the backend defaults to the caller's own company.
import { api, type Paginated } from "@/lib/api";
import { useFetch } from "./useFetch";

interface NamedRow {
  id: string;
  name: string;
}

/** One company on the roster. Picking it in any role fills the project's
 * phone/email alongside the name. */
export interface PartyRow {
  id: string;
  name: string;
  phone: string;
  email: string;
}

interface CurrencyRow {
  id: string;
  code: string;
  name: string;
  is_default: boolean;
}

export function useProjectTypes() {
  return useFetch(() => api.get<Paginated<NamedRow>>("/project-types/?page_size=200"), []);
}

export function useProjectPriorities() {
  return useFetch(() => api.get<Paginated<NamedRow>>("/project-priorities/?page_size=200"), []);
}

export function useCurrencies() {
  return useFetch(() => api.get<Paginated<CurrencyRow>>("/currencies/?page_size=200"), []);
}

/** The one roster behind every party dropdown on the project form. There used
 * to be a hook per role against a list per role, which meant the same company
 * had to be entered up to four times to be pickable everywhere. */
export function useParties() {
  return useFetch(() => api.get<Paginated<PartyRow>>("/parties/?page_size=500"), []);
}
