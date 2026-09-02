import type { CoverageBand, SampleBand } from "@/lib/sample";
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

export interface SourceLoad {
  /** The loader's own source name: `footystats`, `transfermarkt`, `demo`. */
  source: string;
  last_loaded_at: string;
  rows_loaded: number;
}

export interface MetaResponse {
  app_name: string;
  app_mode: AppMode;
  version: string;
  /** Present in demo mode so the UI can show a persistent banner. */
  demo_data_notice: string | null;
  data_sources: DataSourceStatus[];
  /**
   * When each source's data was last loaded, per source and never summed.
   * The performance and market pipelines run on different schedules, so one
   * "updated today" label would be wrong whenever only one of them refreshed —
   * which is the normal case.
   *
   * Empty when nothing has been loaded since load times began to be recorded,
   * or when the database could not be reached. Never inferred from when the
   * checks last ran: that is a different fact and a fresher-sounding one.
   */
  data_freshness: SourceLoad[];
  /** Whether the caller's build token was accepted. False for everyone else. */
  build_access: boolean;
}

/** Error envelope shared by every backend failure response. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ---------------------------------------------------------------------------
// Analytical results (Phase 9)
// ---------------------------------------------------------------------------

/** The population a percentile was measured against. Never hidden. */
export interface ComparisonContext {
  scope: string;
  position_group: string;
  season_id: string;
  competition_ids: string[];
  population_size: number;
  minimum_minutes: number;
  label: string;
  /** Present whenever the comparison spans more than one competition. */
  caveat: string | null;
  strength_adjusted: boolean;
}

export interface Metric {
  metric: string;
  label: string;
  value: number | null;
  percentile: number | null;
  /** A low value is the better outcome, so the UI must say so. */
  lower_is_better: boolean;
  unavailable_reason: string | null;
}

export interface ScoreComponent {
  metric: string;
  label: string;
  weight: number;
  percentile: number | null;
  contribution: number | null;
}

export interface Score {
  key: string;
  label: string;
  /**
   * The weighted profile score, 0-100. For a role this is the Raw Role Fit:
   * explainable and decomposable, and not quite comparable across roles.
   */
  score: number | null;
  coverage: number;
  components: ScoreComponent[];
  missing: string[];
  caveat: string | null;
  /**
   * Roles only. Where the raw score stands among every player evaluated for
   * this same role — the comparable figure, and what the best role is chosen
   * by. Null when too few players were evaluated for a standing to mean
   * anything.
   */
  role_fit_percentile?: number | null;
  /** How many players that standing was measured against. */
  role_population?: number;
}

export interface RoleFit {
  best: Score | null;
  alternatives: Score[];
  /** What a role score does and does not claim. */
  meaning: string;
}

/**
 * What a figure rests on: how much football, and how much of it was recorded.
 *
 * None of this filters anybody. Every player is scored and ranked whatever
 * their minutes; these say how much weight to put on the result.
 */
export interface Sample {
  /** Time on the pitch. */
  minutes: number | null;
  /**
   * The minutes the provider's detailed counts describe - the denominator of
   * every per-90 here. Null when the provider said nothing, which is not the
   * same as nought.
   */
  recorded_minutes: number | null;
  /** recorded / played, as a percentage. Null when it cannot be computed. */
  detailed_coverage_pct: number | null;
  coverage_band: CoverageBand | null;
  coverage_label: string | null;
  coverage_explanation: string | null;
  band: SampleBand;
  band_label: string;
  explanation: string;
}

export interface PlayerSummary {
  player_id: string;
  name: string;
  age: number | null;
  position_group: string;
  raw_position: string | null;
  club: string | null;
  competition: string;
  nationality: string | null;
  minutes: number | null;
  sample_band: SampleBand;
  market_value_eur: number | null;
  contract_expires: string | null;
  best_role: string | null;
  /** Raw Role Fit for the best role. */
  best_role_score: number | null;
  /** Its standing among players evaluated for that same role. */
  best_role_percentile?: number | null;
}

export interface PlayerDetail extends PlayerSummary {
  preferred_foot: string | null;
  height_cm: number | null;
  date_of_birth: string | null;
  is_mock: boolean;
}

export interface PlayerList {
  items: PlayerSummary[];
  total: number;
  offset: number;
  limit: number;
  /** Whether these results are fabricated. A deployment serves one or the other. */
  is_mock: boolean;
}

export interface PlayerStats {
  player_id: string;
  sample: Sample;
  context: ComparisonContext | null;
  metrics: Metric[];
  scores: Score[];
}

export type FeatureCoverageBand = "high" | "good" | "limited" | "very_limited";

export interface SimilarPlayer {
  player: PlayerSummary;
  /** Resemblance on the features the two players share, 0-100. */
  similarity: number;
  shared_features: number;
  /**
   * How many the position's vector defines. Six of eleven is much weaker
   * evidence than eleven of eleven, and the index alone cannot tell them apart
   * — both can read 92. Reported beside it, never mixed into it.
   */
  expected_features: number;
  feature_coverage_pct: number;
  coverage_band: FeatureCoverageBand;
  coverage_label: string;
  /** Low values mean the profiles match in shape but not in strength. */
  profile_strength_ratio: number;
  comparable_strength: boolean;
}

export interface SimilarPlayers {
  target: PlayerSummary;
  results: SimilarPlayer[];
  meaning: string;
}

/** Everything a profile page shows, in one response. */
export interface PlayerProfile {
  player: PlayerDetail;
  stats: PlayerStats;
  /** Null when no role could be fitted; the rest of the profile still stands. */
  roles: RoleFit | null;
  similar: SimilarPlayers;
}

export interface Competition {
  competition_id: string;
  name: string;
  player_count: number;
}

export interface Role {
  key: string;
  label: string;
  description: string;
  position_groups: string[];
  caveat: string | null;
}

export interface RecruitmentCandidate {
  player: PlayerSummary;
  score: number;
  components: ScoreComponent[];
  coverage: number;
}

export interface UnavailableScore {
  key: string;
  label: string;
  missing: string[];
  reason: string;
}

export interface RecruitmentResults {
  items: RecruitmentCandidate[];
  total: number;
  offset: number;
  limit: number;
  context_caveat: string | null;
  considered: number;
  unavailable_scores: UnavailableScore[];
  /**
   * Why the result is empty or short. An empty page from "no player matched
   * these filters" and one from "this score cannot be computed at all" look
   * identical, and only one of them is fixed by widening the filters.
   */
  explanation: string | null;
  /** Whether these results are fabricated. A deployment serves one or the other. */
  is_mock: boolean;
}

export interface ReplacementCandidate {
  player: PlayerSummary;
  overall: number;
  similarity: number;
  role_fit: number | null;
  market_fit: number | null;
  comparable_strength: boolean;
}

export interface ReplacementResults {
  target: PlayerSummary;
  items: ReplacementCandidate[];
  meaning: string;
}

export interface Opportunity {
  player: PlayerSummary;
  best_role_score: number | null;
  reasons: string[];
}

export interface ScreenStep {
  criterion: string;
  remaining: number;
  removed: number;
}

export interface Opportunities {
  items: Opportunity[];
  total: number;
  criteria: string[];
  /** States what the list claims — and, crucially, what it does not. */
  disclaimer: string;
  /**
   * Where the screen narrowed, criterion by criterion. Five criteria and one
   * survivor is either a strict screen or a broken one, and the list alone
   * cannot tell you which.
   */
  funnel: ScreenStep[];
  explanation: string | null;
  /** Whether these results are fabricated. A deployment serves one or the other. */
  is_mock: boolean;
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

/**
 * The signed-in user.
 *
 * Deliberately narrow. The backend never returns the password hash or any
 * session identifier, so neither appears here.
 */
export interface AuthUser {
  user_id: number;
  email: string;
  display_name: string | null;
  created_at: string;
  last_login_at: string | null;
}

// ---------------------------------------------------------------------------
// Shortlists
// ---------------------------------------------------------------------------

export interface Shortlist {
  shortlist_id: number;
  name: string;
  description: string | null;
  entry_count: number;
  created_at: string;
  updated_at: string;
}

export interface ShortlistEntry {
  player_key: string;
  /** Null when the saved player is not in the current data. */
  player: PlayerSummary | null;
  /** The name captured when they were saved. Shown only when `player` is null. */
  saved_as: string | null;
  note: string | null;
  added_at: string;
  unavailable_reason: string | null;
}

export interface ShortlistDetail extends Shortlist {
  entries: ShortlistEntry[];
}

export interface ComparedPlayer {
  player: PlayerSummary;
  sample: Sample;
  note: string | null;
  metrics: Metric[];
  scores: Score[];
  role: Score | null;
}

export interface ComparisonResponse {
  context: ComparisonContext | null;
  players: ComparedPlayer[];
  /** Present when the columns are not measured against the same population. */
  caveat: string | null;
}

// ---------------------------------------------------------------------------
// Data quality
// ---------------------------------------------------------------------------

export type CheckStatus = "pass" | "warn" | "fail";

export interface QualityCheck {
  source: string;
  entity: string;
  check_name: string;
  status: CheckStatus;
  record_count: number;
  detail: string | null;
  executed_at: string;
}

export interface SourceFreshness {
  source: string;
  /** When the checks last ran. */
  last_checked_at: string;
  age_days: number;
  checks_run: number;
  failures: number;
  warnings: number;
  /**
   * When this source's data was last loaded — a different fact from the check
   * time, and the one a reader means by "how current is this?".
   * Null for a source loaded before the two were recorded separately.
   */
  last_loaded_at: string | null;
  data_age_days: number | null;
  rows_loaded: number | null;
}

export interface Volumes {
  players: number;
  competitions: number;
  clubs: number;
  player_seasons: number;
}

export interface IdentityCoverage {
  players: number;
  matched: number;
  /** Not a failure: a player one source knows and the other does not. */
  unmatched: number;
  matched_share: number;
  manual_overrides: number;
  /** Matched on weaker evidence — plausible rather than settled. */
  ambiguous: number;
}

export interface AnalyticsFreshness {
  players: number;
  competitions: number;
  built_at: string | null;
  /** True when the database has moved since this view was built. */
  is_stale: boolean;
}

export interface DataQualityResponse {
  /** What these checks do and do not establish. Always rendered with them. */
  meaning: string;
  /** Set when there is nothing to report, so an empty page cannot look clean. */
  notice: string | null;
  volumes: Volumes;
  sources: SourceFreshness[];
  checks: QualityCheck[];
  identity: IdentityCoverage | null;
  average_detailed_coverage_pct: number | null;
  /** What the provider cannot supply at all. Empty in demo mode. */
  unavailable_metrics: string[];
  analytics: AnalyticsFreshness | null;
}
