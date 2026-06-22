"use client";

// "Show:" level selector + search box for the Schedule tab. Picking a level
// other than "All" flattens the tree into a searchable list of just that level
// (ProjectSchedule swaps in ScheduleFlatList / ScheduleTaskSearch for it).
import { Select } from "@/components/ui/Select";
import styles from "./scheduleTree.module.css";

export type ScheduleFilterType = "all" | "phase" | "zone" | "building" | "area" | "task";

const TYPE_OPTIONS: { value: ScheduleFilterType; label: string }[] = [
  { value: "all", label: "All (tree view)" },
  { value: "phase", label: "Phases" },
  { value: "zone", label: "Zones" },
  { value: "building", label: "Buildings" },
  { value: "area", label: "Areas" },
  { value: "task", label: "Tasks" },
];

interface Props {
  type: ScheduleFilterType;
  onTypeChange: (type: ScheduleFilterType) => void;
  search: string;
  onSearchChange: (search: string) => void;
}

export function ScheduleFilterBar({ type, onTypeChange, search, onSearchChange }: Props) {
  const label = TYPE_OPTIONS.find((o) => o.value === type)?.label.toLowerCase();
  return (
    <div className={styles.filterBar}>
      <Select
        options={TYPE_OPTIONS}
        value={type}
        onChange={(e) => onTypeChange(e.target.value as ScheduleFilterType)}
        aria-label="Filter by level"
      />
      {type !== "all" && (
        <input
          className={styles.search}
          type="search"
          placeholder={`Search ${label}…`}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label={`Search ${label}`}
        />
      )}
    </div>
  );
}
