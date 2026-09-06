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

/** A consultant or contractor: picking one fills the project's phone/email
 * alongside the name. Clients carry a name only (see the master_data models). */
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

export function useClients() {
  return useFetch(() => api.get<Paginated<NamedRow>>("/clients/?page_size=500"), []);
}

export function useConsultants() {
  return useFetch(() => api.get<Paginated<PartyRow>>("/consultants/?page_size=500"), []);
}

export function useContractors() {
  return useFetch(() => api.get<Paginated<PartyRow>>("/contractors/?page_size=500"), []);
}

export function useSubcontractors() {
  return useFetch(() => api.get<Paginated<PartyRow>>("/subcontractors/?page_size=500"), []);
}
