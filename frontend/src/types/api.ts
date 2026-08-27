/**
 * TypeScript mirrors of the backend Pydantic response models.
 *
 * These describe only what the API actually returns. The backend deliberately
 * does not expose scoring formulas, provider field names or credentials, so
 * nothing of that kind should ever appear in this file.
 */

export type AppMode = "demo" | "production";

export type DependencyState = "ok" | "degraded" | "unavailable" | "not_configured";

export interface DependencyStatus {
  name: string;
  status: DependencyState;
  detail: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app_mode: AppMode;
  app_env: string;
  version: string;
  schema_revision: string | null;
  dependencies: DependencyStatus[];
}

export interface DataSourceStatus {
  name: string;
  kind: "performance" | "market";
  /** Concrete provider implementation currently in use. */
  provider: string;
  /** True when the values shown are fabricated demo data. */
  is_mock: boolean;
  /**
   * True only once the provider's real field schema has been profiled and
   * mapped. False means dependent features are intentionally disabled.
   */
  validated: boolean;
  notes: string | null;
}

export interface MetaResponse {
  app_name: string;
  app_mode: AppMode;
  version: string;
  /** Present in demo mode so the UI can show a persistent banner. */
  demo_data_notice: string | null;
  data_sources: DataSourceStatus[];
}

/** Error envelope shared by every backend failure response. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
