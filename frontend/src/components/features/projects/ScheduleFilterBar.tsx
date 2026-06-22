"use client";

// 4 cascading dropdowns above the Schedule tab's Tree/Grid views: Zone -> Subzone
// -> Phase -> Task. Each one only has options (and is enabled) once its parent is
// picked, since that's how the data actually nests. Picking a value prunes
// whichever view is currently showing down to that branch.
import { Select } from "@/components/ui/Select";
import type { Activity, Scope } from "@/types/project";
import styles from "./scheduleTree.module.css";

interface Props {
  zoneOptions: Scope[];
  subzoneOptions: Scope[];
  phaseOptions: Scope[];
  taskOptions: Activity[];
  zone: string;
  subzone: string;
  phase: string;
  task: string;
  onZoneChange: (value: string) => void;
  onSubzoneChange: (value: string) => void;
  onPhaseChange: (value: string) => void;
  onTaskChange: (value: string) => void;
}

export function ScheduleFilterBar({
  zoneOptions, subzoneOptions, phaseOptions, taskOptions,
  zone, subzone, phase, task,
  onZoneChange, onSubzoneChange, onPhaseChange, onTaskChange,
}: Props) {
  return (
    <div className={styles.filterBar}>
      <Select
        aria-label="Filter by zone"
        value={zone}
        onChange={(e) => onZoneChange(e.target.value)}
        options={[{ value: "", label: "All zones" }, ...zoneOptions.map((s) => ({ value: s.id, label: s.name }))]}
      />
      <Select
        aria-label="Filter by subzone"
        value={subzone}
        disabled={!zone}
        onChange={(e) => onSubzoneChange(e.target.value)}
        options={[{ value: "", label: "All subzones" }, ...subzoneOptions.map((s) => ({ value: s.name, label: s.name }))]}
      />
      <Select
        aria-label="Filter by phase"
        value={phase}
        disabled={!subzone}
        onChange={(e) => onPhaseChange(e.target.value)}
        options={[{ value: "", label: "All phases" }, ...phaseOptions.map((s) => ({ value: s.name, label: s.name }))]}
      />
      <Select
        aria-label="Filter by task"
        value={task}
        disabled={!phase}
        onChange={(e) => onTaskChange(e.target.value)}
        options={[{ value: "", label: "All tasks" }, ...taskOptions.map((a) => ({ value: a.name, label: a.name }))]}
      />
    </div>
  );
}
