// Types for the Settings module — mirror the backend settings serializers.

export interface CompanyInfo {
  id: string;
  name: string;
  slug: string;
  is_platform_admin: boolean;
  is_active: boolean;
  phone_number: string;
  email: string;
  address: string;
  website: string;
  user_count: number;
  created_at: string;
}

export interface CompanyRow {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  is_platform_admin: boolean;
  user_count: number;
  created_at: string;
}

export interface UserRow {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone_number: string;
  is_active: boolean;
  roles: string[];
  role_ids: string[];
  company_name: string;
  created_at: string;
}

export interface RoleRow {
  id: string;
  name: string;
  is_platform_role: boolean;
  is_system: boolean;
  is_locked: boolean;
  permissions: string[];
  member_count: number;
  created_at: string;
}

export interface PermissionItem {
  key: string;
  label: string;
}

export interface PermissionGroup {
  group: string;
  permissions: PermissionItem[];
}
