"use client";

// Picks a client / consultant / contractor from the company's Master Data
// list (Settings -> Master Data) instead of retyping the name on every
// project. The project still stores the plain name, exactly as before — see
// apps/master_data/models.py, where every list works this way.
import { Select } from "@/components/ui/Select";

export interface PartyOption {
  id: string;
  name: string;
  phone?: string;
  email?: string;
}

interface Props {
  label: string;
  name: string;
  /** The name currently stored on the project. */
  value: string;
  options: PartyOption[];
  /** True until the list has arrived — the one option shown is the stored
   * value, so an edit form never flashes as though the field were empty. */
  loading?: boolean;
  /** The picked row, or null for the blank option. `name` is what to store. */
  onPick: (row: PartyOption | null, name: string) => void;
}

/** "— none —" is a real, selectable value: every stakeholder field on a
 * project is optional, so the form has to be able to clear one. */
const NONE = "";

export function PartySelect({ label, name, value, options, loading, onPick }: Props) {
  const known = options.some((o) => o.name === value);
  const choices = [
    { value: NONE, label: loading ? "Loading…" : "— none —" },
    ...options.map((o) => ({ value: o.name, label: o.name })),
    // These fields were free text before this list existed, so a project can
    // legitimately hold a name nobody has added to Master Data. Showing it as
    // an option keeps it selected and saveable — dropping it would silently
    // blank the field the first time someone opened an older project to edit
    // something unrelated.
    ...(value && !known && !loading
      ? [{ value, label: `${value} (not in the list)` }]
      : []),
  ];

  return (
    <Select
      label={label}
      name={name}
      value={value}
      options={choices}
      onChange={(e) => {
        const picked = e.target.value;
        onPick(options.find((o) => o.name === picked) ?? null, picked);
      }}
    />
  );
}
