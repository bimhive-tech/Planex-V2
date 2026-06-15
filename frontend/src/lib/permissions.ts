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
  SUBMIT_PROGRESS: "submit_progress",
  REVIEW_PROGRESS: "review_progress",
  APPROVE_PROGRESS: "approve_progress",
  EXPORT_REPORTS: "export_reports",
} as const;

export type PermissionKey = (typeof Permission)[keyof typeof Permission];

export function hasPermission(user: { permissions: string[] } | null, key: string): boolean {
  return !!user && user.permissions.includes(key);
}
