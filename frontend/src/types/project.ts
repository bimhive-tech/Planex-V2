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
  created_at: string;
  updated_at: string;
}

export type ScopeType = "phase" | "zone" | "building" | "area";

export interface Scope {
  id: string;
  parent: string | null;
  scope_type: ScopeType;
  scope_type_display: string;
  name: string;
  sort_order: number;
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
  activities: Activity[];
}
