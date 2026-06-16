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
  status: ReportStatus;
  project: string;
  project_name: string;
  template: string | null;
  template_name: string | null;
  period_start: string | null;
  period_finish: string | null;
  created_at: string;
}
