// Cross-project Approvals inbox types — mirror the backend ApprovalsInboxView.
import type { ProjectSubmission } from "./project";

export interface InboxSubmission extends ProjectSubmission {
  project_id: string;
  project_name: string;
}

export interface InboxResponse {
  results: InboxSubmission[];
  review_count: number;
  approve_count: number;
}
