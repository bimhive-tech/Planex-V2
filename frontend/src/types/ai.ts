// AI assistant types — mirror apps/ai_assistant serializers + SSE event shapes.

export interface ChatSessionRow {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatAttachmentRow {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
}

export type ChatRole = "user" | "assistant" | "tool" | "system";

export interface ChatMessageRow {
  id: string;
  role: ChatRole;
  content: string;
  tool_name: string;
  created_at: string;
  attachments: ChatAttachmentRow[];
}

export interface AiProposal {
  valid: boolean;
  action: "create_project" | "import_tree";
  summary: string;
  errors?: unknown;
  [key: string]: unknown;
}

export type AiStreamEvent =
  | { type: "delta"; content: string }
  | { type: "proposal"; message_id: string; proposal: AiProposal }
  | { type: "done" }
  | { type: "error"; message: string };
