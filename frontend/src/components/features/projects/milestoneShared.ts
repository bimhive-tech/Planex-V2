// Shared Milestone type + status options — used by the Overview highlights
// card (MilestonesPanel) and the full Milestones tab (ProjectMilestones).
export interface Milestone {
  id: string;
  title: string;
  date: string | null;
  status: string;
  status_display: string;
  sort_order: number;
  // From the source file's own "Activity % Complete" column when a P6 import
  // set one — null for a manually added milestone or a row the file left
  // blank (never coerced to 0, so the UI can tell those apart).
  progress_percent: string | null;
  scope_id: string | null;
  // Ancestor chain top-down (e.g. ["PH1", "Z(A)", "Building 15"]) when a P6
  // import tied this milestone to a specific zone/building — null for
  // project-wide milestones and any manually added one.
  scope_path: string[] | null;
}

export const MILESTONE_STATUSES = [
  { value: "completed", label: "Completed" },
  { value: "in_progress", label: "In Progress" },
  { value: "upcoming", label: "Upcoming" },
];

export function milestoneCompletionPct(items: Milestone[]): number | null {
  if (items.length === 0) return null;
  const completed = items.filter((m) => m.status === "completed").length;
  return Math.round((completed / items.length) * 100);
}
