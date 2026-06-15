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
  created_at: string;
  updated_at: string;
}
