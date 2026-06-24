// Sidebar navigation config. `permission` gates visibility; `soon` marks
// modules not yet built (shown but non-navigable) so the structure is visible.
import { ROUTES } from "@/lib/constants";
import { Permission } from "@/lib/permissions";

export interface NavItem {
  label: string;
  href: string;
  icon: string; // key into the icon set
  permission?: string; // required permission to see the item
  anyPermission?: string[]; // visible if the user holds ANY of these
  platformOnly?: boolean;
  soon?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: ROUTES.dashboard, icon: "dashboard" },
  { label: "Projects", href: "/projects", icon: "projects", permission: Permission.VIEW_PROJECTS },
  {
    label: "Approvals", href: ROUTES.approvals, icon: "check",
    anyPermission: [Permission.REVIEW_PROGRESS, Permission.APPROVE_PROGRESS],
  },
  { label: "Reports", href: "/reports", icon: "reports", permission: Permission.VIEW_PROJECTS },
  // Settings is always shown (the Info subtab is available to every user);
  // its subtabs self-filter by permission.
  { label: "Settings", href: ROUTES.settings, icon: "settings" },
];
