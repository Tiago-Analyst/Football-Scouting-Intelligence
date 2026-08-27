/**
 * Server-side client for the FastAPI backend.
 *
 * The `server-only` import makes it a build error to pull this module into a
 * client component. That enforces the intended request path:
 *
 *     Browser -> Next.js (server) -> FastAPI -> PostgreSQL
 *
 * The browser never talks to FastAPI directly and never sees provider
 * credentials, so `API_BASE_URL` is intentionally NOT a NEXT_PUBLIC_ variable.
 */
import "server-only";

import type { ApiErrorBody } from "@/types/api";

const DEFAULT_TIMEOUT_MS = 8_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The FastAPI origin. Exported for callers that fetch a non-JSON body. */
export function baseUrl(): string {
  const url = process.env.API_BASE_URL;
  if (!url) {
    throw new Error(
      "API_BASE_URL is not set. Copy frontend/.env.local.example to frontend/.env.local.",
    );
  }
  return url.replace(/\/+$/, "");
}

interface ApiFetchOptions {
  /** Seconds to cache the response. Omit for always-fresh reads. */
  revalidate?: number;
  signalTimeoutMs?: number;
  /** Defaults to GET. */
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** JSON body, for the search endpoints that take a filter object. */
  body?: unknown;
  /**
   * Raw `Cookie` header to forward to FastAPI.
   *
   * The browser's session cookie is set on the Next.js origin, so it never
   * reaches FastAPI on its own. Authenticated calls have to relay it
   * explicitly, and only the calls that need it do — a request that does not
   * pass this sends no session at all.
   */
  cookie?: string;
  /** Statuses to treat as a parseable answer rather than an error. */
  acceptStatuses?: number[];
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  /** `Set-Cookie` values from FastAPI, for the caller to relay onward. */
  setCookie: string[];
}

/**
 * Fetch and parse a JSON endpoint, normalising backend error envelopes into
 * `ApiError`. Network and timeout failures surface as `ApiError` with status 0
 * so callers have a single failure type to handle.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  return (await apiFetchWithHeaders<T>(path, options)).data;
}

/**
 * As `apiFetch`, but also returns the status and any `Set-Cookie` FastAPI
 * issued. Sign-in needs both: the session token exists only in that header —
 * deliberately, since putting it in the JSON body would expose it to any
 * client-side code that renders the response.
 */
export async function apiFetchWithHeaders<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<ApiResponse<T>> {
  const { revalidate, signalTimeoutMs = DEFAULT_TIMEOUT_MS, method = "GET", body } = options;
  const url = `${baseUrl()}${path.startsWith("/") ? path : `/${path}`}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(options.cookie ? { Cookie: options.cookie } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(signalTimeoutMs),
      // Only a plain GET may be cached. A POST is a search here rather than a
      // mutation, but the body decides the result and Next keys its cache on
      // the URL alone; and a cookie-bearing response is specific to one
      // signed-in person, so it must never enter a shared cache either.
      ...(revalidate === undefined || method !== "GET" || options.cookie
        ? { cache: "no-store" }
        : { next: { revalidate } }),
    });
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : "unknown error";
    throw new ApiError(`Could not reach the API at ${url}: ${reason}`, 0, "network_error");
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new ApiError("API returned a malformed JSON response.", response.status, "bad_response");
    }
  }

  const accepted = response.ok || (options.acceptStatuses?.includes(response.status) ?? false);
  if (!accepted) {
    const body = parsed as ApiErrorBody | null;
    throw new ApiError(
      body?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      body?.error?.code ?? "http_error",
    );
  }

  return { data: parsed as T, status: response.status, setCookie: response.headers.getSetCookie() };
}
