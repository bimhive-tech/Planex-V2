// Mirror of backend apps/accounts/constants.py Permission keys. Keep in sync.
export const Permission = {
  MANAGE_COMPANIES: "manage_companies",
  MANAGE_PLATFORM: "manage_platform",
  MANAGE_COMPANY: "manage_company",
  MANAGE_USERS: "manage_users",
  MANAGE_ROLES: "manage_roles",
  MANAGE_DEPARTMENTS: "manage_departments",
  MANAGE_PROJECTS: "manage_projects",
  VIEW_PROJECTS: "view_projects",
  VIEW_SCHEDULE: "view_schedule",
  SUBMIT_PROGRESS: "submit_progress",
  REVIEW_PROGRESS: "review_progress",
  APPROVE_PROGRESS: "approve_progress",
  DELETE_PROGRESS_IMAGES: "delete_progress_images",
  EXPORT_REPORTS: "export_reports",
  VIEW_FINANCES: "view_finances",
  MANAGE_FINANCES: "manage_finances",
  VIEW_AREAS_OF_CONCERN: "view_areas_of_concern",
  MANAGE_AREAS_OF_CONCERN: "manage_areas_of_concern",
  VIEW_SUBMITTALS: "view_submittals",
  MANAGE_SUBMITTALS: "manage_submittals",
} as const;

export type PermissionKey = (typeof Permission)[keyof typeof Permission];

export function hasPermission(user: { permissions: string[] } | null, key: string): boolean {
  return !!user && user.permissions.includes(key);
}
