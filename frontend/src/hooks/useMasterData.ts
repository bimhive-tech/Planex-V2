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
