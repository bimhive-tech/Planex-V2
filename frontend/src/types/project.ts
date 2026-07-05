// Project types — mirror the backend project serializers.

export interface ProjectListRow {
  id: string;
  name: string;
  code: string;
  project_type: string;
  project_type_display: string;
  priority: string;
  location: string;
  client_name: string;
  planned_start: string | null;
  planned_finish: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail {
  id: string;
  name: string;
  code: string;
  project_type: string;
  project_type_display: string;
  priority: string;
  priority_display: string;
  budget: string | null;
  currency: string;
  location: string;
  description: string;
  client_name: string;
  consultant_name: string;
  consultant_phone: string;
  consultant_email: string;
  contractor_name: string;
  contractor_phone: string;
  contractor_email: string;
  planned_start: string | null;
  planned_finish: string | null;
  revised_finish: string | null;
  size_sqm: string | null;
  notes: string;
  is_archived: boolean;
  overall_progress: number;
  activity_count: number;
  progress_breakdown: ProgressBreakdown;
  team_count: number;
  open_submission_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectSubmission {
  id: string;
  activity: string;
  activity_name: string;
  activity_path: string;
  previous_progress: string;
  submitted_progress: string;
  status: string;
  status_display: string;
  note: string;
  review_comment: string;
  submitted_by_name: string;
  reviewed_by_name: string;
  approved_by_name: string;
  images: { id: string; url: string; caption: string; created_at: string }[];
  reviewed_at: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

// Module access comes from the user's COMPANY role permissions (consistent
// everywhere in the app); scope (which data within a module) is the only thing
// configured per-project-member. See ProjectMember below.
export interface ProjectPerms {
  manage: boolean; // MANAGE_PROJECTS — admin actions (edit project, manage team, structural edits)
  viewSchedule: boolean;
  submit: boolean;
  review: boolean;
  approve: boolean;
  deletePhotos: boolean;
  viewAreasOfConcern: boolean;
  manageAreasOfConcern: boolean;
  viewSubmittals: boolean;
  manageSubmittals: boolean;
  viewFinances: boolean;
  manageFinances: boolean;
  exportReports: boolean;
}

export type ProjectImageType = "site_photo" | "cover" | "logo_left" | "logo_right";

export interface ProjectImage {
  id: string;
  image_type: ProjectImageType;
  image_type_display: string;
  caption: string;
  sort_order: number;
  url: string;
  created_at: string;
  updated_at: string;
}

// A dated progress reading for an activity (the history behind its current %).
export interface ProgressEntry {
  id: string;
  date: string;
  progress_percent: string;
  note: string;
  recorded_by_name: string;
  can_edit: boolean;
  created_at: string;
}

// A progress photo as returned by the history/gallery endpoint.
export interface ProgressImage {
  id: string;
  url: string;
  caption: string;
  date: string;
  activity_id: string;
  activity_name: string;
  phase_name: string;
  subzone_code: string;
  uploaded_by_name: string;
  created_at: string;
}

export interface ProjectMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  // The user's actual company role(s) (Settings -> Roles) — read-only display;
  // there's no separate per-project role anymore.
  role_names: string[];
}

export interface ProgressBreakdown {
  total: number;
  completed: number;
  in_progress: number;
  not_started: number;
}

export type ScopeType = "phase" | "zone" | "building" | "area";

export type ScopeDiscipline = "concrete" | "architecture" | "electrical" | "mechanical" | "other" | "";

export interface Scope {
  id: string;
  parent: string | null;
  scope_type: ScopeType;
  scope_type_display: string;
  name: string;
  sort_order: number;
  planned_start: string | null;
  planned_finish: string | null;
  revised_finish: string | null;
  discipline: ScopeDiscipline;
  discipline_display: string;
}

export interface Activity {
  id: string;
  scope: string;
  name: string;
  code: string;
  unit: string;
  progress_type: "percentage" | "quantity";
  progress_type_display: string;
  planned_quantity: string | null;
  weight: string;
  progress_percent: string;
  sort_order: number;
}

export interface ProjectStructure {
  overall_progress: number;
  scope_progress: Record<string, number>;
  scopes: Scope[];
  scope_activity_counts: Record<string, number>;
  activity_count: number;
  progress_breakdown: ProgressBreakdown;
}

// Excel grid (one zone): subzones across columns, tasks down the rows.
export interface GridCell {
  id: string;
  progress: string;
}
export interface GridRow {
  row_index: number;
  name: string;
  phase: string;
  weight: string;
  cells: (GridCell | null)[];
}
export interface ZoneGrid {
  zone: { id: string; name: string };
  subzones: { id: string; name: string }[];
  rows: GridRow[];
}
