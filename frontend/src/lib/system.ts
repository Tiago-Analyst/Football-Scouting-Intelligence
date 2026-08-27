/** Typed accessors for the backend system endpoints. */
import "server-only";

import { apiFetch } from "@/lib/api";
import type { DataQualityResponse, HealthResponse, MetaResponse } from "@/types/api";

/**
 * Readiness of the backend and its dependencies.
 *
 * A degraded backend answers 503 with a populated body describing which
 * dependency failed. That is a status report, not a transport failure, so 503
 * is accepted and rendered. `null` means the backend was genuinely unreachable.
 */
export async function getHealth(): Promise<HealthResponse | null> {
  try {
    return await apiFetch<HealthResponse>("/health", { acceptStatuses: [503] });
  } catch {
    return null;
  }
}

/** Application metadata: mode banner and data provenance. */
export async function getMeta(): Promise<MetaResponse | null> {
  try {
    return await apiFetch<MetaResponse>("/api/v1/meta", { revalidate: 60 });
  } catch {
    return null;
  }
}

/**
 * The data quality report.
 *
 * Never cached: the point of the page is to say how current the data is, and
 * serving a stale answer to that question would be self-defeating.
 */
export async function getDataQuality(): Promise<DataQualityResponse | null> {
  try {
    return await apiFetch<DataQualityResponse>("/api/v1/data-quality");
  } catch {
    // The page renders an explicit failure state rather than an error boundary:
    // "we cannot tell you about data quality right now" is itself the answer.
    return null;
  }
}
