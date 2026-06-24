// In-app notification types — mirror the backend NotificationSerializer.

export interface NotificationItem {
  id: string;
  kind: string;
  kind_display: string;
  message: string;
  project_id: string | null;
  actor_name: string;
  is_read: boolean;
  created_at: string;
}

export interface NotificationsResponse {
  results: NotificationItem[];
  unread_count: number;
}
