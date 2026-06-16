// Report + template shapes shared across the Reports module.

// The template config is deeply nested and fully editable; treat it as an
// open record and read/write via dot-paths (see lib/reportTemplate).
export type ReportConfig = Record<string, unknown>;

export interface ReportTemplate {
  id: string;
  name: string;
  config: ReportConfig;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export type ReportStatus = "draft" | "submitted" | "approved";

export interface ReportRow {
  id: string;
  title: string;
  report_number: string;
  report_date: string | null;
  status: ReportStatus;
  project: string;
  project_name: string;
  template: string | null;
  template_name: string | null;
  period_start: string | null;
  period_finish: string | null;
  description: string;
  created_at: string;
}

// Computed report data pulled from the chosen project (for the builder's
// read-only Project Info + Progress Report tabs).
export interface ReportData {
  overall: number;
  breakdown: { total: number; completed: number; in_progress: number; not_started: number };
  zones: { name: string; progress: number }[];
  milestones: { title: string; date: string | null; status: string }[];
  snapshots: { date: string | null; overall_progress: number; source: string }[];
  project: {
    name: string; type: string; location: string; client: string;
    consultant: string; contractor: string; planned_start: string | null;
    planned_finish: string | null; size_sqm: string | null; budget: string | null; currency: string;
  };
}

// Per-report content image (cover / progress photo / attachment).
export type ReportImageKind = "cover" | "progress" | "attachment";

export interface ReportImage {
  id: string;
  kind: ReportImageKind;
  kind_display: string;
  caption: string;
  sort_order: number;
  url: string;
  created_at: string;
}
