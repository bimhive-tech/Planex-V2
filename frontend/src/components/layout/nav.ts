// Sidebar navigation config. `permission` gates visibility; `soon` marks
// modules not yet built (shown but non-navigable) so the structure is visible.
import { ROUTES } from "@/lib/constants";
import { Permission } from "@/lib/permissions";

export interface NavItem {
  label: string;
  href: string;
  icon: string; // key into the icon set
  permission?: string; // required permission to see the item
  platformOnly?: boolean;
  soon?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: ROUTES.dashboard, icon: "dashboard" },
  { label: "Projects", href: "/projects", icon: "projects", permission: Permission.VIEW_PROJECTS, soon: true },
  { label: "User Management", href: "/users", icon: "users", permission: Permission.MANAGE_USERS, soon: true },
  { label: "Companies", href: "/companies", icon: "companies", platformOnly: true, soon: true },
];
