"""API response models.

What the frontend receives. Deliberately *results*, not implementations: no
weights, no formulas, no provider field names (spec section 28). A score arrives
with the components that produced it, because a recruitment ranking has to be
explainable — but the definition that produced it stays server-side.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ComparisonContextOut(BaseModel):
    """The population a percentile was measured against.

    Always returned with a percentile. Section 25 forbids hiding the reference
    group, and a rank without one cannot be interpreted.
    """

    scope: str
    position_group: str
    season_id: str
    competition_ids: list[str]
    population_size: int
    minimum_minutes: int
    label: str
    caveat: str | None = None
    strength_adjusted: bool = False


class MetricOut(BaseModel):
    """One metric with its rank."""

    metric: str
    label: str
    value: float | None
    percentile: float | None
    #: True when a low value is the better outcome, so the UI can say so.
    lower_is_better: bool = False
    unavailable_reason: str | None = None


class ScoreComponentOut(BaseModel):
    metric: str
    label: str
    weight: float
    percentile: float | None
    contribution: float | None = None


class ScoreOut(BaseModel):
    """An intelligence score or role fit, with its decomposition."""

    key: str
    label: str
    score: float | None
    coverage: float
    components: list[ScoreComponentOut]
    missing: list[str] = Field(default_factory=list)
    caveat: str | None = None


class RoleFitOut(BaseModel):
    best: ScoreOut | None
    alternatives: list[ScoreOut] = Field(default_factory=list)
    #: What the number does and does not claim. Returned so it cannot be
    #: separated from the score in the UI.
    meaning: str


class SampleOut(BaseModel):
    minutes: int | None
    band: str
    explanation: str


class PlayerSummary(BaseModel):
    """A player as they appear in a list."""

    player_id: str
    name: str
    age: int | None
    position_group: str
    raw_position: str | None
    club: str | None
    competition: str
    nationality: str | None
    minutes: int | None
    sample_band: str
    market_value_eur: int | None
    contract_expires: date | None
    best_role: str | None
    best_role_score: float | None


class PlayerDetail(PlayerSummary):
    """A player profile."""

    preferred_foot: str | None
    height_cm: int | None
    date_of_birth: date | None
    is_mock: bool


class PlayerListResponse(BaseModel):
    """A page of players.

    Section 27: recruitment searches are paginated. Twenty thousand players must
    never be sent to a browser to be filtered there.
    """

    items: list[PlayerSummary]
    total: int
    offset: int
    limit: int


class PlayerStatsResponse(BaseModel):
    player_id: str
    sample: SampleOut
    context: ComparisonContextOut | None
    metrics: list[MetricOut]
    scores: list[ScoreOut]


class SimilarPlayerOut(BaseModel):
    player: PlayerSummary
    similarity: float
    shared_features: int
    #: How comparable the two profiles are in strength, 0-1. A high similarity
    #: with a low ratio means the shapes match but the levels do not.
    profile_strength_ratio: float
    comparable_strength: bool


class SimilarPlayersResponse(BaseModel):
    target: PlayerSummary
    results: list[SimilarPlayerOut]
    meaning: str


class MarketValuePointOut(BaseModel):
    valued_on: date
    market_value_eur: int


class TransferOut(BaseModel):
    transfer_date: date | None
    season: str | None
    from_club: str | None
    to_club: str | None
    fee_eur: int | None
    transfer_type: str


class CompetitionOut(BaseModel):
    competition_id: str
    name: str
    player_count: int


class RoleOut(BaseModel):
    key: str
    label: str
    description: str
    position_groups: list[str]
    caveat: str | None = None


class RecruitmentWeights(BaseModel):
    """User-defined emphasis across intelligence scores.

    Weights are normalised server-side, so a profile adding to 99 shifts
    emphasis rather than rescaling every result.
    """

    weights: dict[str, float] = Field(
        description="Intelligence score key to weight. At least one is required."
    )


class RecruitmentFilters(BaseModel):
    position_groups: list[str] | None = None
    min_age: int | None = None
    max_age: int | None = None
    max_market_value_eur: int | None = None
    min_market_value_eur: int | None = None
    competitions: list[str] | None = None
    nationalities: list[str] | None = None
    preferred_foot: str | None = None
    min_height_cm: int | None = None
    min_minutes: int | None = None
    contract_expiring_within_months: int | None = None


class RecruitmentRequest(RecruitmentWeights):
    filters: RecruitmentFilters = Field(default_factory=RecruitmentFilters)
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class RecruitmentCandidate(BaseModel):
    player: PlayerSummary
    score: float
    #: Why this player ranked here: the component percentiles behind the score.
    components: list[ScoreComponentOut]
    coverage: float


class UnavailableScoreOut(BaseModel):
    """A requested score that could not be produced, and what it needed."""

    key: str
    label: str
    #: The component metrics the provider does not supply.
    missing: list[str]
    reason: str


class RecruitmentResponse(BaseModel):
    items: list[RecruitmentCandidate]
    total: int
    offset: int
    limit: int
    context_caveat: str | None = None
    #: How many players the filters admitted, before scoring.
    considered: int = 0
    #: Requested scores that no candidate could be given.
    unavailable_scores: list[UnavailableScoreOut] = Field(default_factory=list)
    #: Plain-language account of an empty or short result.
    #:
    #: An empty page from "no player matched these filters" and one from "this
    #: score cannot be computed from the data at all" look identical, and a
    #: recruiter would reasonably narrow their filters in response to the
    #: second - which can never help.
    explanation: str | None = None


class ReplacementRequest(BaseModel):
    player_id: str
    filters: RecruitmentFilters = Field(default_factory=RecruitmentFilters)
    limit: int = Field(default=25, ge=1, le=100)


class ReplacementCandidate(BaseModel):
    player: PlayerSummary
    overall: float
    similarity: float
    role_fit: float | None
    market_fit: float | None
    comparable_strength: bool


class ReplacementResponse(BaseModel):
    target: PlayerSummary
    items: list[ReplacementCandidate]
    #: Stated with the results: this ranks a statistical profile, not a person.
    meaning: str


class OpportunityOut(BaseModel):
    player: PlayerSummary
    best_role_score: float | None
    reasons: list[str]


class OpportunitiesResponse(BaseModel):
    items: list[OpportunityOut]
    total: int
    criteria: list[str]
    #: Section 16 forbids calling a player undervalued without a validated
    #: valuation model. This states what the list does claim.
    disclaimer: str


# ---------------------------------------------------------------------------
# Shortlists
# ---------------------------------------------------------------------------


class ShortlistOut(BaseModel):
    """A shortlist as it appears in the list of them."""

    shortlist_id: int
    name: str
    description: str | None
    entry_count: int
    created_at: datetime
    updated_at: datetime


class ShortlistEntryOut(BaseModel):
    """One saved player.

    `player` is None when the saved key no longer resolves in the current
    analytical view — a competition dropped from the load, a provider that
    stopped returning them. The entry is still returned, with the name captured
    when it was saved, because quietly deleting someone's saved player is worse
    than showing them a gap.
    """

    player_key: str
    player: PlayerSummary | None
    #: Name at the time of saving. Shown only when `player` is None.
    saved_as: str | None
    note: str | None
    added_at: datetime
    unavailable_reason: str | None = None


class ShortlistDetail(ShortlistOut):
    entries: list[ShortlistEntryOut]


class ComparedPlayer(BaseModel):
    """One column of a comparison."""

    player: PlayerSummary
    sample: SampleOut
    note: str | None
    metrics: list[MetricOut]
    scores: list[ScoreOut]
    role: ScoreOut | None


class ComparisonResponse(BaseModel):
    """Players side by side, with the population they are all ranked against."""

    context: ComparisonContextOut | None
    players: list[ComparedPlayer]
    #: Present when the selection spans position groups or competitions, where
    #: a straight column-by-column read is misleading.
    caveat: str | None = None


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


class QualityCheckOut(BaseModel):
    """One automated check, as it was recorded when it ran."""

    source: str
    entity: str
    check_name: str
    status: Literal["pass", "warn", "fail"]
    record_count: int
    detail: str | None
    executed_at: datetime


class SourceFreshnessOut(BaseModel):
    source: str
    last_checked_at: datetime
    age_days: int
    checks_run: int
    failures: int
    warnings: int


class VolumesOut(BaseModel):
    players: int
    competitions: int
    clubs: int
    player_seasons: int


class DataQualityResponse(BaseModel):
    """What was checked, when, and what it found."""

    #: What these checks do and do not establish. Returned so it cannot be
    #: separated from the ticks in the UI.
    meaning: str
    #: Set when there is nothing to report, so the page cannot look reassuring
    #: by being empty.
    notice: str | None
    volumes: VolumesOut
    sources: list[SourceFreshnessOut]
    checks: list[QualityCheckOut]
