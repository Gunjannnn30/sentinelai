// Thin fetch wrapper for the SentinelAI API.
//
// Auth is cookie based: the backend sets an httponly `sentinel_session` cookie
// plus a JS-readable `sentinel_csrf` cookie. Every unsafe request (POST/PUT/
// PATCH/DELETE) must echo the CSRF cookie in the `X-CSRF-Token` header or the
// backend answers 403 `csrf_failed` (see backend/app/core/security.py).

import type { ApiErrorBody } from "./types";

/**
 * Base URL for API calls. Empty by default => same-origin, which is what the
 * Next.js rewrite proxy expects (see next.config.ts). The proxy forwards
 * `/api/*`, `/health`, `/ready` and `/metrics` to the backend, so the browser
 * never makes a cross-origin request and the auth cookies stay first-party.
 *
 * Set NEXT_PUBLIC_API_URL to an absolute origin ONLY if the backend itself
 * sends permissive CORS headers — otherwise the browser will block the calls.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/** All feature routes live under this prefix; /health and /ready do not. */
export const API_V1 = `${API_BASE}/api/v1`;

export const CSRF_COOKIE = "sentinel_csrf";
export const SESSION_COOKIE = "sentinel_session";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Parse a `document.cookie`-style string for one cookie name. */
export function readCookie(
  name: string,
  cookieString: string =
    typeof document === "undefined" ? "" : document.cookie,
): string | null {
  for (const part of cookieString.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(`${name}=`)) {
      return decodeURIComponent(trimmed.slice(name.length + 1));
    }
  }
  return null;
}

/**
 * Headers for one request. Unsafe methods get `X-CSRF-Token` whenever the CSRF
 * cookie exists; GETs never do.
 */
export function csrfHeaders(
  method: string,
  cookie: string | null = readCookie(CSRF_COOKIE),
): Record<string, string> {
  if (!UNSAFE_METHODS.has(method.toUpperCase())) return {};
  if (!cookie) return {};
  return { "X-CSRF-Token": cookie };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string;
  readonly retryAfter: string | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: unknown;
    requestId?: string;
    retryAfter?: string | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? null;
    this.requestId = init.requestId ?? "";
    this.retryAfter = init.retryAfter ?? null;
  }
}

/** Turn a backend error envelope into an ApiError. */
export function apiErrorFromBody(
  status: number,
  body: unknown,
  retryAfter: string | null = null,
): ApiError {
  const envelope = (body as ApiErrorBody | null)?.error;
  if (envelope && typeof envelope.message === "string") {
    return new ApiError({
      status,
      code: envelope.code ?? "unknown",
      message: envelope.message,
      details: envelope.details ?? null,
      requestId: envelope.request_id ?? "",
      retryAfter,
    });
  }
  return new ApiError({
    status,
    code: `http_${status}`,
    message: `The server responded with status ${status}.`,
    retryAfter,
  });
}

export interface ApiRequestInit {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * Fetch a backend path (absolute, e.g. `${API_V1}/models`). Always sends
 * cookies; attaches the CSRF header on unsafe methods. Throws `ApiError` for
 * any 4xx/5xx. A 204 resolves to `undefined`.
 */
export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { ...csrfHeaders(method) };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "include",
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: "Could not reach the SentinelAI API. Is the backend running?",
    });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    // A live session that the server no longer accepts: let the auth provider
    // notice and bounce the user to /login instead of showing a raw 401.
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("sentinel:unauthorized"));
    }
    throw apiErrorFromBody(
      response.status,
      parsed,
      response.headers.get("Retry-After"),
    );
  }

  return parsed as T;
}

/** Convenience builders for query strings (undefined/null values dropped). */
export function qs(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}
