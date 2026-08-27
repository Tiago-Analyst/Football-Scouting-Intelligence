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

function baseUrl(): string {
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
  /**
   * Non-2xx statuses to treat as a successful, parseable response.
   *
   * Readiness is the motivating case: a degraded backend answers /health with
   * 503 and a populated body describing which dependency is down. That body is
   * the report we want to render, not an error to swallow.
   */
  acceptStatuses?: number[];
}

/**
 * Fetch and parse a JSON endpoint, normalising backend error envelopes into
 * `ApiError`. Network and timeout failures surface as `ApiError` with status 0
 * so callers have a single failure type to handle.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { revalidate, signalTimeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const url = `${baseUrl()}${path.startsWith("/") ? path : `/${path}`}`;

  let response: Response;
  try {
    response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(signalTimeoutMs),
      ...(revalidate === undefined ? { cache: "no-store" } : { next: { revalidate } }),
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

  return parsed as T;
}
