// Single browser API client. Same-origin requests with cookies; parses the
// DRF error envelope into a typed ApiError. No scattered fetch() calls.
import { API_BASE } from "./constants";
import type { ApiErrorBody } from "@/types/auth";

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;

  constructor(status: number, code: string, message: string, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface RequestOptions extends RequestInit {
  json?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const init: RequestInit = {
    ...rest,
    credentials: "include", // send/receive httpOnly auth cookies
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
  };
  if (json !== undefined) init.body = JSON.stringify(json);

  const res = await fetch(`${API_BASE}${path}`, init);

  if (res.status === 204) return undefined as T;

  const body = await res.json().catch(() => null);

  if (!res.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? "Something went wrong. Please try again.",
      err?.details ?? null,
    );
  }
  return body as T;
}

// Note: `path` is origin-relative as given (NOT prefixed with API_BASE), because
// large uploads go through a Next route handler at /upload/... not the /api proxy.
async function upload<T>(path: string, file: File, field = "file"): Promise<T> {
  const body = new FormData();
  body.append(field, file);
  const res = await fetch(path, { method: "POST", credentials: "include", body });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (data as ApiErrorBody | null)?.error;
    throw new ApiError(res.status, err?.code ?? "error", err?.message ?? "Upload failed.", err?.details ?? null);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", json }),
  patch: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", json }),
  put: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", json }),
  del: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
  upload,
};

/** Standard DRF page-number response shape. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
