// Shared auth types — mirror the backend CurrentUserSerializer shape.

export interface CompanyBrief {
  id: string;
  name: string;
  slug: string;
  is_platform_admin: boolean;
}

export interface CurrentUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone_number: string;
  company: CompanyBrief | null;
  is_platform_admin: boolean;
  permissions: string[];
  roles: string[];
}

// Error envelope returned by the DRF custom exception handler.
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
  };
}
