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

export interface SourcePublication {
  /** The loader's own source name: `footystats`, `transfermarkt`, `demo`. */
  source: string;
  /**
   * When this source's data was published — the moment what the reader is
   * looking at became these figures. Not when a load ran: loads write to a
   * staging schema, and one that fails its checks never reaches production.
   */
  last_published_at: string;
  rows_published: number;
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
  data_freshness: SourcePublication[];
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
  /** "Central Midfielders", not "CM". */
  position_label: string;
  season_id: string;
  competition_ids: string[];
  /** Display names for those ids, in the same order. */
  competition_names: string[];
  population_size: number;
  /**
   * The floor a caller asked for. Nought by default, because minutes do not
   * decide who is compared — so do not render it unconditionally.
   */
  minimum_minutes: number;
  /** Server-assembled one-liner. Prefer the parts above for display. */
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
  /**
   * The same value ranked against every loaded competition rather than the
   * player's own. Null when `percentile` is already global.
   *
   * The gap between the two is the point. Neither is adjusted for league
   * strength, so a player 92nd at home and 61st across Europe has not been
   * judged worse - they have been put in a bigger room.
   */
  global_percentile: number | null;
  /** A low value is the better outcome, so the UI must say so. */
  lower_is_better: boolean;
  unavailable_reason: string | null;
}

/** How much of a role's own definition was available to score it. */
export type RoleCoverageBand = "full" | "reduced" | "limited";

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
   * What the score measures, in a sentence. A label like "Ball Progression"
   * gives a reader the topic and not the claim, and a number nobody can
   * interpret is a number nobody should act on.
   */
  description?: string | null;
  /**
   * The weighted profile score, 0-100. For a role this is the Raw Role Fit:
   * explainable and decomposable, and not quite comparable across roles.
   */
  score: number | null;
  coverage: number;
  components: ScoreComponent[];
  missing: string[];
  /** Hand-written, and qualitative only: limits no report can derive. */
  caveat: string | null;
  /** Roles only. What was missing, generated from what was actually missing. */
  availability_note?: string | null;
  /** The two above joined, so they cannot be shown apart or out of order. */
  explanation?: string | null;
  /**
   * Roles only. Where the raw score stands among every player evaluated for
   * this same role — the comparable figure, and what the best role is chosen
   * by. Null when too few players were evaluated for a standing to mean
   * anything.
   */
  role_fit_percentile?: number | null;
  /** How many players that standing was measured against. */
  role_population?: number;
  /** Roles only. `coverage` banded: full, reduced or limited. */
  coverage_band?: RoleCoverageBand | null;
  coverage_label?: string | null;
  /**
   * True when enough of the role's definition is missing that its label
   * overstates what was measured. The score is real; the name is generous.
   */
  is_limited?: boolean;
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
   * The minutes the provider's detailed counts describe, and the denominator
   * of the rates built from them — passing, tackling, shooting, npxG, xA.
   * Not of every per-90: goals, assists and goals conceded are top-level
   * counters and divide by `minutes`, which is what the provider's own
   * published per-90 figures for them reproduce against.
   * Null when the provider said nothing, which is not the same as nought.
   */
  recorded_minutes: number | null;
  /** recorded / played as a percentage, capped at 100 for display. */
  detailed_coverage_pct: number | null;
  /** The uncapped ratio. May exceed 100; for data quality, not for display. */
  detailed_coverage_raw_pct?: number | null;
  /** True when the provider reported more detail-minutes than played-minutes. */
  provider_minutes_inconsistent?: boolean;
  minutes_discrepancy_label?: string | null;
  minutes_discrepancy_explanation?: string | null;
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
  /** The population behind `Metric.global_percentile`. */
  global_context: ComparisonContext | null;
  metrics: Metric[];
  scores: Score[];
}

export type FeatureCoverageBand = "high" | "good" | "limited" | "very_limited";

/**
 * One feature, on both sides of a similarity comparison.
 *
 * The index says two profiles resemble each other; these say where. Both
 * values are null under a representation with no percentile to report, rather
 * than carrying a number invented to fill the column.
 */
export interface FeatureComparison {
  metric: string;
  label: string;
  /** Distance on the comparison scale. Small is alike. */
  gap: number;
  target: number | null;
  candidate: number | null;
}

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
  /** Where the two profiles are closest. What drove the index. */
  drivers?: FeatureComparison[];
  /** Where they are furthest apart, furthest first. */
  differences?: FeatureComparison[];
}

export interface SimilarPlayers {
  target: PlayerSummary;
  results: SimilarPlayer[];
  meaning: string;
}

/** Everything a profile page shows, in one response. */
export interface MarketValuePoint {
  valued_on: string;
  market_value_eur: number;
}

export interface Transfer {
  transfer_date: string | null;
  season: string | null;
  from_club: string | null;
  to_club: string | null;
  /** Null when the source does not report one, which is not the same as free. */
  fee_eur: number | null;
  transfer_type: string;
}

/** One reading, with the number it came from. */
export interface Finding {
  label: string;
  /** Oriented so higher is always better, whichever way the metric reads. */
  percentile: number;
  reading: string;
}

/**
 * The profile's own numbers, read aloud.
 *
 * Every line is a threshold applied to a figure shown elsewhere on the page.
 * Computed on the server, like everything analytical: the frontend renders it
 * and does not decide any of it.
 */
export interface ScoutingInterpretation {
  profile: string[];
  strengths: Finding[];
  watch_outs: Finding[];
  /** Metrics the provider does not supply — not things the player does badly. */
  unavailable: string[];
  confidence: string[];
  /** What the model does not look at. Never shown without the reading. */
  not_captured: string[];
}

export interface PlayerProfile {
  player: PlayerDetail;
  stats: PlayerStats;
  /** Null when no role could be fitted; the rest of the profile still stands. */
  roles: RoleFit | null;
  similar: SimilarPlayers;
  /** Both empty for a player the market source does not cover. */
  market_value_history: MarketValuePoint[];
  transfers: Transfer[];
  /** Null when there is nothing to read from. */
  interpretation?: ScoutingInterpretation | null;
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

/**
 * A named role, expressed as recruitment-builder weights.
 *
 * A starting point the user can see and change, not a second ranking. Roles
 * are defined mostly in metrics and the builder weights the eight
 * intelligence scores, so part of a role can have nowhere to go:
 * `expressible` is the share that survived and `unmapped` names the rest.
 */
export interface RolePreset {
  key: string;
  label: string;
  description: string;
  position_groups: string[];
  /** Intelligence score key -> weight, in steps of five, summing to 100. */
  weights: Record<string, number>;
  /** Share of the role's own definition these weights carry, 0-1. */
  expressible: number;
  caveat: string | null;
  /** Role components no intelligence score covers, by label. */
  unmapped: string[];
  /**
   * Scores this preset weights that the loaded data cannot produce. A preset
   * with any of these ranks nobody, whatever the filters say.
   */
  unavailable_scores: UnavailableScore[];
}

/** One emphasis, and whether this load can produce it at all. */
export interface ScoreAvailability {
  key: string;
  label: string;
  description: string;
  available: boolean;
  /** Component metrics the provider does not supply. Empty when available. */
  missing: string[];
  reason: string | null;
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

/** One step in the shortlist workflow, served so nothing drifts apart. */
export interface ShortlistStatus {
  key: string;
  label: string;
  description: string;
}

export interface ShortlistEntry {
  player_key: string;
  /** Null when the saved player is not in the current data. */
  player: PlayerSummary | null;
  /** The name captured when they were saved. Shown only when `player` is null. */
  saved_as: string | null;
  /**
   * Where this player has got to in the owner's own process. A workflow state
   * the owner set, never something the system concluded, and it changes no
   * score anywhere.
   */
  status: string;
  status_label: string;
  note: string | null;
  /** The argument, split, so a one-sided entry is visible as one. */
  pros: string | null;
  concerns: string | null;
  /** Null until the owner records a judgement. Saving is not reviewing. */
  last_reviewed_at: string | null;
  added_at: string;
  unavailable_reason: string | null;
}

export interface ShortlistDetail extends Shortlist {
  entries: ShortlistEntry[];
}

export interface ComparedPlayer {
  player: PlayerSummary;
  sample: Sample;
  /** Where the owner has got to with this player. */
  status: string;
  status_label: string;
  note: string | null;
  pros: string | null;
  concerns: string | null;
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
  /**
   * The refresh generation this check describes, and whether that generation
   * was a candidate in staging or is the dataset being served. Null on rows
   * recorded before generations carried context.
   */
  /** The refresh this check describes: a FootyStats generation, or an id minted for a Transfermarkt refresh. */
  refresh_id?: string | null;
  generation_id?: string | null;
  context?: "CANDIDATE" | "PUBLISHED" | null;
}

/**
 * Checks describing a refresh nobody is being served yet — one between
 * staging and production, or one that failed to reach it. Kept apart from
 * `checks` because the page used to mix them: production serving G4, a G5
 * candidate checked and then failed at promotion, every tick describing G5.
 */
export interface CandidateChecks {
  source: string;
  refresh_id: string;
  /** FootyStats only. Null for a provider with no generation model. */
  generation_id?: string | null;
  executed_at: string;
  checks: QualityCheck[];
}

/** The checks that validated the dataset this source is serving. */
export interface PublishedChecks {
  source: string;
  refresh_id: string | null;
  generation_id: string | null;
  published_at: string | null;
  executed_at: string | null;
  checks: QualityCheck[];
}

/** One source, two datasets, kept apart: what is serving and what waits. */
export interface ProviderQuality {
  source: string;
  published: PublishedChecks | null;
  /** Null when no refresh is between staging and production. */
  candidate: CandidateChecks | null;
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
   * When this source's data was last *published* — a different fact from the
   * check time, and the one a reader means by "how current is this?".
   * Null for a source published before publications were recorded.
   */
  last_published_at: string | null;
  data_age_days: number | null;
  rows_published: number | null;
  /**
   * When a refresh last loaded this source into staging, published or not.
   * Operational: newer than `last_published_at` means a refresh is stuck between
   * staging and production, not that the data on screen has changed.
   */
  last_load_attempt_at: string | null;
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

/** Where the FootyStats refresh has got to. Operational, never internal. */
export interface RefreshGeneration {
  generation_id: string;
  status: string;
  created_at: string | null;
  last_updated_at: string | null;
  published_at: string | null;
  total_expected_players: number;
  completed_players: number;
  failed_players: number;
  completion_pct: number;
  competitions_complete: number;
  competitions_expected: number;
  complete: boolean;
}

export interface RefreshStatus {
  state: string;
  published: RefreshGeneration | null;
  current: RefreshGeneration | null;
}

/** A canonical metric the provider cannot supply, and what was found. */
export interface MetricAvailability {
  metric: string;
  label: string;
  /** Null when nothing was recorded. Absent evidence is stated as absent. */
  reason: string | null;
}

/** A metric with no provider field, computed from ones that exist. */
export interface DerivedMetricNote {
  metric: string;
  label: string;
  /** The arithmetic, so the claim can be checked rather than believed. */
  formula: string;
}

export interface DataQualityResponse {
  /** What these checks do and do not establish. Always rendered with them. */
  meaning: string;
  /** Set when there is nothing to report, so an empty page cannot look clean. */
  notice: string | null;
  volumes: Volumes;
  sources: SourceFreshness[];
  /** The most recent checks describing the dataset being served. */
  checks: QualityCheck[];
  /** The generation `checks` describe, when the publication ledger names one. */
  published_generation_id?: string | null;
  /** Checks about a refresh that has not reached readers. Never about the data on screen. */
  candidate?: CandidateChecks[];
  /** The same facts per source, published beside candidate. */
  providers?: ProviderQuality[];
  identity: IdentityCoverage | null;
  average_detailed_coverage_pct: number | null;
  /** What the provider cannot supply at all. Empty in demo mode. */
  unavailable_metrics: string[];
  /** The same metrics with the evidence that established each absence. */
  unavailable_detail: MetricAvailability[];
  /** Metrics with no provider field that the system computes anyway. */
  derived_metrics: DerivedMetricNote[];
  analytics: AnalyticsFreshness | null;
  /** Null when no generation exists yet. */
  refresh?: RefreshStatus | null;
}
