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
    #: What to call the position group in front of a reader: "Central
    #: Midfielders", not "CM". The code stays above for callers that key on it.
    position_label: str = ""
    season_id: str
    competition_ids: list[str]
    #: Display names for those competitions, in the same order.
    #:
    #: The ids are source-prefixed keys - `footystats:12345` - which are
    #: correct, stable and meaningless to a reader. They used to reach the
    #: profile through `label`, which is why this exists.
    competition_names: list[str] = Field(default_factory=list)
    population_size: int
    #: How far into their seasons the competitions in this population are.
    #:
    #: An all-leagues rank sounds like a comparison with the wider game. On
    #: the loaded data it is mostly a comparison with two matches: nine of 44
    #: competitions contain a player who has reached a full season's minutes,
    #: and 82% of the population comes from the other 35. The percentile is an
    #: honest rank within the population it names; this says what that
    #: population is made of, so the name cannot be read as something broader.
    competitions_in_population: int = 0
    competitions_established: int = 0
    established_share: float = 1.0
    median_minutes: int = 0
    #: One sentence, or null when every competition here has played enough and
    #: there is nothing worth saying.
    maturity_note: str | None = None
    #: True when most of this population has barely started its season.
    is_early_season: bool = False
    #: The minutes floor a caller asked for, which is nought by default because
    #: minutes do not decide who is compared.
    #:
    #: Kept so a caller who set one can see it honoured. It is not something to
    #: render unprompted: "players with at least 0 minutes" is the sentence
    #: that made this comment necessary.
    minimum_minutes: int
    label: str
    caveat: str | None = None
    strength_adjusted: bool = False


class MetricOut(BaseModel):
    """One metric with its rank."""

    metric: str
    label: str
    value: float | None
    #: Rank in the metric's own direction: a high percentile for
    #: `dispossessed_per90` means dispossessed often. Kept because it is the
    #: rank in the distribution and sometimes that is the question.
    percentile: float | None
    #: The same rank oriented so higher is always better.
    #:
    #: This is what the site displays. A metric table that printed "4th" for a
    #: player who is rarely dispossessed, beside a Scouting Interpretation
    #: calling the same figure a strength, was two pages disagreeing about one
    #: number - and 4 reads as bad to everyone who has not stopped to work out
    #: which way the metric runs.
    performance_percentile: float | None = None
    #: The same value ranked against every loaded competition rather than the
    #: player's own. Present only when `percentile` is a domestic rank, so the
    #: two are never the same number printed twice.
    #:
    #: The gap between them is the point. Neither is adjusted for league
    #: strength - nothing in this system is - so a player at the 92nd
    #: percentile at home and the 61st across Europe has not been judged
    #: weaker; they have been placed in a bigger room. Which of the two to
    #: believe is a recruitment judgement, and showing both is what lets
    #: somebody make it.
    global_percentile: float | None = None
    #: Oriented, like `performance_percentile`, so the two columns on a row
    #: can be read against each other.
    global_performance_percentile: float | None = None
    #: True when a low value is the better outcome, so the UI can say so.
    lower_is_better: bool = False
    #: Which band of play the metric describes - passing, duels, goalkeeping.
    #: Presentation only: nothing is computed per family, and a table that
    #: ignores it reads exactly as it did before.
    family: str | None = None
    unavailable_reason: str | None = None


class CoreDimensionOut(BaseModel):
    """One football concept a role is defined by, and whether anything measured it."""

    name: str
    satisfied: bool
    #: Metrics that evidenced it, and metrics that could have and did not.
    #: Both, because "aerial efficiency: missing aerial_duel_win_percentage"
    #: tells a reader what to go and look for.
    available: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ScoreEvidenceOut(BaseModel):
    """How many events a score rests on, when it rests on few.

    Reported beside the percentile and never folded into it. A score built
    from success rates - goals per shot, dribbles completed per attempt - is
    noise when the denominator is small, and minutes played cannot tell you
    that: a full season of football can contain four shots.
    """

    #: The count the provider supplied.
    events: int
    #: What to call them: "shots", "dribbles attempted".
    noun: str
    #: The configured floor below which this is not offered as a strength.
    threshold: int
    #: True when the count is under that floor.
    low: bool
    #: One phrase for a page, e.g. "Low evidence - 8 shots".
    label: str


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
    #: What the score is measuring, in a sentence. Shown as a tooltip, because
    #: a label like "Ball Progression" tells a reader the topic and not the
    #: claim - and a number nobody can interpret is a number nobody should act
    #: on.
    description: str | None = None
    #: The weighted profile score, 0-100. For a role this is the Raw Role Fit:
    #: explainable, decomposable, and not quite comparable across roles.
    score: float | None
    coverage: float
    components: list[ScoreComponentOut]
    missing: list[str] = Field(default_factory=list)
    #: full | partial | unavailable, for a role. Absent for intelligence scores.
    #:
    #: Separate from `coverage` on purpose. Coverage answers how much of the
    #: configured definition could be measured; validity answers whether the
    #: concepts that make the role that role are measurable at all. A
    #: percentage cannot tell those apart, which is how a centre-back with no
    #: measure of progression came to be ranked as a ball-playing centre-back.
    validity: str | None = None
    #: Each defining concept and what evidenced it, so a page can name the one
    #: that is missing rather than saying "partial" and stopping.
    core_dimensions: list[CoreDimensionOut] = Field(default_factory=list)
    #: Why no standard percentile is published, when none is. Null when one is.
    role_fit_percentile_reason: str | None = None
    #: The component carrying an unusually large share of what the score
    #: actually came out as, when one does.
    #:
    #: Weights say what a role intends to measure; contributions say what it
    #: ended up measuring for this player. They diverge, and a validation
    #: audit found an Advanced Playmaker whose xA alone produced 44% of his
    #: realised score - a role named for creation behaving like a ranking of
    #: one metric. Explanatory, not punitive: nothing is reweighted and the
    #: score is unchanged.
    dominant_component: str | None = None
    #: Its share of the realised total, 0-100.
    dominant_share: float | None = None
    #: The countable events behind this score, for the scores whose components
    #: are success rates. Null where the question does not arise.
    evidence: ScoreEvidenceOut | None = None
    #: Hand-written, and deliberately qualitative only: methodological limits
    #: that no availability report can derive.
    caveat: str | None = None
    #: Roles only. What was missing, generated from what was actually missing.
    #:
    #: Availability claims used to live in `caveat` and went stale exactly as
    #: one would expect - the Ball-Winning Midfielder apologised for a score
    #: that had been available for months, and the Direct Winger for a metric
    #: it was not missing at all.
    availability_note: str | None = None
    #: The two above, joined, so the interface cannot show them apart.
    explanation: str | None = None
    #: Roles only. Where the raw score sits among every player evaluated for
    #: this same role.
    #:
    #: Raw role scores do not share a scale: a role whose weight sits mostly on
    #: one component inherits that component's spread, while a role averaging
    #: six evenly weighted components is pulled towards the middle. Comparing
    #: 72 against 78 across two such roles compares distributions rather than
    #: players. This number is measured within one distribution, so it can be
    #: compared - and it is what the best role is chosen by.
    role_fit_percentile: float | None = None
    #: How many players that standing was measured against. Absent standing
    #: with a small population means the role had too few to rank within.
    role_population: int = 0
    #: Roles only. `coverage` banded: full, reduced or limited.
    #:
    #: Needed because the score itself cannot show it. Missing components have
    #: their weight renormalised across what remains - otherwise absent data
    #: would read as poor performance - and after that a score built from 60%
    #: of a definition looks exactly like one built from all of it.
    coverage_band: str | None = None
    coverage_label: str | None = None
    #: True when enough of the definition is missing that the role's label
    #: overstates what was measured. The score is real; the name is generous.
    is_limited: bool = False


class UnscoredRoleOut(BaseModel):
    """A role this player could have been measured for, and why they were not.

    "No role fit could be computed." was the whole message, on profiles with
    a full season played and most of their metrics present. It told a reader
    nothing they could act on and nothing they could check. Every figure here
    is read back from the role engine - the role's own configured minimum, the
    coverage actually reached, and the components that were absent - so the
    page cannot drift from what the scorer did.
    """

    key: str
    label: str
    #: Share of the role's definition that was measurable, 0-100.
    coverage_pct: float
    #: What this role requires before it will produce a score, 0-100.
    required_pct: float
    #: The components that were not available, by display label.
    missing: list[str] = Field(default_factory=list)


class RoleFitOut(BaseModel):
    best: ScoreOut | None
    alternatives: list[ScoreOut] = Field(default_factory=list)
    #: Roles whose defining concepts this data cannot fully measure, strongest
    #: raw fit first. Beside the best role, never as it: a partial score is a
    #: real number and an unfair comparison, so it is reported and not ranked
    #: against fully supported roles.
    partial_evidence: list[ScoreOut] = Field(default_factory=list)
    #: Roles that were tried and could not be scored, with the shortfall.
    #: Populated when there is no best role, which is when a reader needs it.
    unscored: list[UnscoredRoleOut] = Field(default_factory=list)
    #: One sentence naming the reason, or null when a role was produced.
    unscored_reason: str | None = None
    #: What the number does and does not claim. Returned so it cannot be
    #: separated from the score in the UI.
    meaning: str


class SampleOut(BaseModel):
    """What a figure rests on: how much football, and how much of it was recorded.

    None of this filters anybody. Every player is scored and ranked whatever
    their minutes; these fields let a reader see how much weight to put on the
    result, which is a different question and theirs to answer.
    """

    #: Time on the pitch.
    minutes: int | None
    #: The minutes the provider's detailed counts actually describe - the
    #: denominator of every per-90 here. Absent when the provider said nothing,
    #: which is not the same as nought.
    recorded_minutes: int | None = None
    #: recorded / played, as a percentage, capped at 100 for display.
    #:
    #: Capped because the raw ratio can exceed 100 - the provider sometimes
    #: reports more detail-minutes than played-minutes - and "127% Excellent
    #: coverage" reads as a broken site rather than as the provider anomaly it
    #: is. `detailed_coverage_raw_pct` carries the uncapped figure.
    detailed_coverage_pct: float | None = None
    #: The uncapped ratio, for data quality and debugging. May exceed 100.
    detailed_coverage_raw_pct: float | None = None
    #: How much of the profile's metric set this player actually has, 0-100.
    #:
    #: A third, separate thing from the two above, and the reason it exists:
    #: a validation audit found a profile carrying "Established Sample" and
    #: "100% detailed coverage" that produced no role, no intelligence score
    #: and nine of eighteen metrics. Neither existing label was wrong - one
    #: counts minutes played, the other the share of those minutes the
    #: provider described in detail - but together they read as "this profile
    #: is complete", and it was not. Minutes are not metrics.
    metric_coverage_pct: float | None = None
    #: The two halves of that fraction, so a page can say "9 of 18".
    metrics_available: int | None = None
    metrics_expected: int | None = None
    #: True when the provider reported more detail-minutes than played-minutes.
    provider_minutes_inconsistent: bool = False
    #: Why, when it did.
    minutes_discrepancy_label: str | None = None
    minutes_discrepancy_explanation: str | None = None
    #: excellent | good | partial | limited, or absent with the percentage.
    coverage_band: str | None = None
    coverage_label: str | None = None
    coverage_explanation: str | None = None
    #: very_low | low | developing | established.
    band: str
    band_label: str
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
    #: The role's identifier, beside its English label.
    #:
    #: Additive and nullable on purpose. The label is prose and belongs to
    #: whoever is reading; the key is an identifier and is the same in every
    #: language, so a localised frontend renders from this and never by
    #: matching the English sentence it used to print. Existing readers of
    #: `best_role` are unaffected.
    best_role_key: str | None = None
    #: Raw Role Fit for the best role: the weighted profile score.
    best_role_score: float | None
    #: Where that raw score stands among players evaluated for the same role.
    #: The comparable figure, and the one the best role was chosen by.
    best_role_percentile: float | None = None


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
    #: Whether these results are fabricated.
    #:
    #: A deployment serves one or the other - fabricated data may not share a
    #: database with real data - so this is a property of the response rather
    #: than of each row. Three pages hardcoded a "Demo data" badge instead, and
    #: went on showing it once the data was real: a warning that is always on is
    #: a warning nobody reads, and this one was telling a recruiter that real
    #: footballers were invented.
    is_mock: bool = False


class PlayerStatsResponse(BaseModel):
    player_id: str
    sample: SampleOut
    context: ComparisonContextOut | None
    #: The population behind `MetricOut.global_percentile`. None when the
    #: percentiles are already global, because then there is no second
    #: population to describe.
    global_context: ComparisonContextOut | None = None
    metrics: list[MetricOut]
    scores: list[ScoreOut]


class FeatureComparisonOut(BaseModel):
    """One feature, on both sides of a similarity comparison.

    The index says two profiles resemble each other; these say where. An index
    of 91 built on ball progression and one built on defensive volume describe
    different players, and the number alone cannot tell them apart.

    `target` and `candidate` are percentiles within the comparison population.
    Both are null under a representation that has no percentile to report,
    rather than carrying a number invented to fill the column.
    """

    metric: str
    label: str
    #: Distance between the two on the comparison scale. Small is alike.
    gap: float
    target: float | None = None
    candidate: float | None = None


class SimilarPlayerOut(BaseModel):
    player: PlayerSummary
    similarity: float
    shared_features: int
    #: How many the position's vector defines. Six of eleven is much weaker
    #: evidence than eleven of eleven, and the index alone cannot tell them
    #: apart - both can read 92.
    expected_features: int = 0
    #: shared / expected, as a percentage.
    feature_coverage_pct: float = 0.0
    #: high | good | limited | very_limited, with its label. Reported beside
    #: the index, never mixed into it.
    coverage_band: str = "high"
    coverage_label: str = ""
    #: What the list was ordered by.
    #:
    #: `similarity` above is the index and is untouched. This is that index
    #: after being pulled toward the average for this search in proportion to
    #: how little football stands behind it - a full season's minutes leaves it
    #: alone. It exists because a per-90 figure from 28 minutes used to be
    #: ranked level with one from 2,195, and nothing in the ordering could tell
    #: them apart.
    ranking_similarity: float = 0.0
    #: 0-1, from minutes alone. 1.0 means the index was ranked as it stands.
    evidence_weight: float = 1.0
    #: One sentence saying why this candidate ranks below its index, or null
    #: when the ordering used the index as it is. Never a bare adjusted number.
    ranking_note: str | None = None
    #: How comparable the two profiles are in strength, 0-1. A high similarity
    #: with a low ratio means the shapes match but the levels do not.
    profile_strength_ratio: float
    comparable_strength: bool
    #: Where the two profiles are closest. What drove the index.
    drivers: list[FeatureComparisonOut] = Field(default_factory=list)
    #: Where they are furthest apart, furthest first. Shipped beside the
    #: drivers rather than instead of them: a panel showing only agreement
    #: would be an argument rather than a comparison.
    differences: list[FeatureComparisonOut] = Field(default_factory=list)


class SimilarPlayersResponse(BaseModel):
    target: PlayerSummary
    results: list[SimilarPlayerOut]
    meaning: str


class FindingOut(BaseModel):
    """One reading, with the number it came from.

    The evidence travels with the claim so an interface cannot show one
    without the other. A sentence without its figure is an opinion.
    """

    label: str
    #: Oriented so higher is always better, whichever way the metric reads.
    percentile: float
    reading: str


class ScoutingInterpretationOut(BaseModel):
    """The profile's own numbers, read aloud.

    Derived entirely from the figures elsewhere in this response - thresholds
    applied to percentiles the reader can see above. Nothing here is a second
    opinion, and no language model is involved: the vocabulary is a fixed list
    chosen so a sentence cannot claim more than a percentile supports.
    """

    profile: list[str] = Field(default_factory=list)
    strengths: list[FindingOut] = Field(default_factory=list)
    watch_outs: list[FindingOut] = Field(default_factory=list)
    #: Metrics the provider does not supply. Named apart from the watch-outs,
    #: because a statistic nobody collected is not something a player does
    #: badly.
    unavailable: list[str] = Field(default_factory=list)
    confidence: list[str] = Field(default_factory=list)
    #: What the model does not look at. Returned with the reading rather than
    #: written into a template, so it cannot be shown without it.
    not_captured: list[str] = Field(default_factory=list)


class PlayerProfileResponse(BaseModel):
    """Everything one profile page shows, in a single answer.

    The page needs four things and used to ask for them separately. That is
    fine for one reader and not fine for a deploy that renders every profile
    ahead of time: four requests a page against five and a half thousand pages
    is twenty-two thousand round trips, and the API's rate limit - rightly -
    refuses to serve them.

    Composed from the same functions the individual endpoints use, so the two
    routes cannot answer differently. Those endpoints stay; this is an addition
    for callers that want the whole page at once.
    """

    player: PlayerDetail
    stats: PlayerStatsResponse
    #: Absent when no role could be fitted, which the individual endpoint
    #: reports as a 404. Not an error here: the rest of the profile stands.
    roles: RoleFitOut | None
    similar: SimilarPlayersResponse
    #: Both empty for a player the market source does not cover, which is an
    #: ordinary state rather than a failure.
    market_value_history: list[MarketValuePointOut] = Field(default_factory=list)
    transfers: list[TransferOut] = Field(default_factory=list)
    #: The figures above, read. Absent when there is nothing to read from -
    #: a player with no ranked metric and no fitted role.
    interpretation: ScoutingInterpretationOut | None = None


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


class ShortlistStatusOut(BaseModel):
    """One step in the shortlist workflow, with what it means.

    Served so the picker, the table and the CSV cannot drift apart, and so a
    desk reads the five words the same way.
    """

    key: str
    label: str
    description: str


class UnavailableScoreOut(BaseModel):
    """A requested score that could not be produced, and what it needed."""

    key: str
    label: str
    #: The component metrics the provider does not supply.
    missing: list[str]
    reason: str


class ScoreAvailabilityOut(BaseModel):
    """One intelligence score, and whether this load can produce it at all.

    Served so the builder can say which emphasis is unavailable *before* a
    search is run. A weight on a score no player can be given matches nobody,
    however wide the filters are, and finding that out from an empty result
    blames the filters for the data.
    """

    key: str
    label: str
    description: str
    available: bool
    #: Component metrics the provider does not supply. Empty when available.
    missing: list[str] = Field(default_factory=list)
    reason: str | None = None


class RolePresetOut(BaseModel):
    """A named role expressed as recruitment-builder weights.

    A starting point the user can see and change, not a second ranking. The
    search that follows is the ordinary weighted search over these numbers.

    `expressible` is the share of the role's own definition the eight
    intelligence scores could carry. Below 1.0 some of what the role measures
    has no score to go to and was dropped rather than redistributed, and
    `unmapped` names what.
    """

    key: str
    label: str
    description: str
    position_groups: list[str]
    #: Share of the preset's configured weight this load can actually measure,
    #: 0-100.
    #:
    #: Different from `expressible`, which is about the mapping from a role to
    #: the eight scores and does not change with the data. This is about the
    #: data in front of you. A validation audit found that thirteen of the
    #: fourteen presets carry at least one dimension the provider cannot
    #: supply, and that zeroing them - which is what the product tells a
    #: reader to do - removes 55% of the Ball-Playing Centre-Back profile
    #: while leaving the name on it. The search then measures ball security
    #: and defensive activity and is still called ball-playing.
    #:
    #: Nothing is substituted and no weight is invented. The number exists so
    #: the warning can come before the search rather than after.
    measurable_pct: float = 100.0
    #: Short status for a badge: full | limited | minimal.
    coverage_status: str = "full"
    #: One sentence for a reader about to run this preset, or null at full
    #: coverage.
    coverage_note: str | None = None
    #: Intelligence score key -> weight, in steps of five, summing to 100.
    weights: dict[str, float]
    expressible: float
    caveat: str | None = None
    unmapped: list[str] = Field(default_factory=list)
    #: Scores this preset weights that the loaded data cannot produce. A
    #: preset with any of these ranks nobody, and says so before it is used
    #: rather than after the search comes back empty.
    unavailable_scores: list[UnavailableScoreOut] = Field(default_factory=list)


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
    #: What the list was ordered by: `score` pulled toward the average for
    #: this search in proportion to how little football stands behind it. A
    #: full season's minutes leaves it untouched. The score itself is never
    #: rewritten, and nobody is excluded for having played less.
    ranking_score: float = 0.0
    #: 0-1, from minutes alone.
    evidence_weight: float = 1.0
    #: One sentence explaining a lower placement, or null when the ordering
    #: used the score as it stands.
    ranking_note: str | None = None


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
    #: Whether these results are fabricated.
    #:
    #: A deployment serves one or the other - fabricated data may not share a
    #: database with real data - so this is a property of the response rather
    #: than of each row. Three pages hardcoded a "Demo data" badge instead, and
    #: went on showing it once the data was real: a warning that is always on is
    #: a warning nobody reads, and this one was telling a recruiter that real
    #: footballers were invented.
    is_mock: bool = False


class ReplacementRequest(BaseModel):
    player_id: str
    filters: RecruitmentFilters = Field(default_factory=RecruitmentFilters)
    limit: int = Field(default=25, ge=1, le=100)


class ReplacementCandidate(BaseModel):
    player: PlayerSummary
    #: Null when a component the score needs could not be computed.
    #:
    #: Renormalising around a missing part used to produce a number that
    #: looked comparable and was not: because similarity is the largest of the
    #: three weights, losing role fit RAISED the result. Candidates missing a
    #: required part now carry no overall rather than a flattering one, and
    #: are listed after the ones whose score means the same thing.
    overall: float | None = None
    similarity: float
    role_fit: float | None
    market_fit: float | None
    comparable_strength: bool
    #: Which required parts were unavailable. Empty for a complete score.
    missing_components: list[str] = Field(default_factory=list)
    #: Minutes behind the candidate's figures, carried for the ordering.
    candidate_minutes: int | None = None
    #: What this group was ordered by: the overall for complete candidates,
    #: the similarity for the rest, each adjusted for how much evidence
    #: stands behind it. Never shown in place of the real number.
    ranking_value: float = 0.0
    evidence_weight: float = 1.0
    ranking_note: str | None = None


class ReplacementResponse(BaseModel):
    target: PlayerSummary
    items: list[ReplacementCandidate]
    #: How many leading items carry a complete, comparable overall score. The
    #: rest follow under limited evidence and are ordered by similarity.
    complete_count: int = 0
    #: Stated with the results: this ranks a statistical profile, not a person.
    meaning: str


class OpportunityOut(BaseModel):
    player: PlayerSummary
    #: The Raw Role Fit, untouched. This is the analytical figure and it is
    #: not what the list is ordered by.
    best_role_score: float | None
    reasons: list[str]
    #: What the list IS ordered by: `best_role_score` pulled toward the average
    #: for this screen in proportion to how little football stands behind it.
    #:
    #: This is a discovery surface, and it was ranking a 98 from 24 minutes
    #: above a 93 from a season. Both are honest percentiles; they are not
    #: equally strong evidence that the player is worth a phone call, and the
    #: order was treating them as if they were. The same adjustment the
    #: replacement finder and the recruitment builder already use, so there is
    #: one formula rather than a second opinion.
    #:
    #: Nobody is excluded, no minutes floor is introduced, and the Raw Role Fit
    #: and Role Fit Percentile are unchanged. A short-sample player who is
    #: genuinely exceptional still places well; three minutes no longer carries
    #: the confidence of eighteen hundred.
    ranking_score: float = 0.0
    #: 0-1, from minutes alone.
    evidence_weight: float = 1.0
    #: One sentence explaining a lower placement, or null when the ordering
    #: used the fit as it stands.
    ranking_note: str | None = None


class ScreenStepOut(BaseModel):
    """One criterion, and how many players were still standing after it."""

    criterion: str
    remaining: int
    removed: int


class OpportunitiesResponse(BaseModel):
    items: list[OpportunityOut]
    total: int
    criteria: list[str]
    #: Section 16 forbids calling a player undervalued without a validated
    #: valuation model. This states what the list does claim.
    disclaimer: str
    #: Where the screen narrowed, criterion by criterion.
    #:
    #: A screen over five criteria that returns one player is either strict or
    #: broken, and the list alone cannot tell you which. Showing the funnel
    #: turns "why is this empty" from a guess into a reading.
    funnel: list[ScreenStepOut] = Field(default_factory=list)
    #: Present when the result is small enough to need accounting for.
    explanation: str | None = None
    #: Whether these results are fabricated.
    #:
    #: A deployment serves one or the other - fabricated data may not share a
    #: database with real data - so this is a property of the response rather
    #: than of each row. Three pages hardcoded a "Demo data" badge instead, and
    #: went on showing it once the data was real: a warning that is always on is
    #: a warning nobody reads, and this one was telling a recruiter that real
    #: footballers were invented.
    is_mock: bool = False


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
    #: Where this player has got to in the owner's own process. A workflow
    #: state the owner set, never something the system concluded, and it
    #: changes no score anywhere.
    status: str
    status_label: str
    note: str | None
    #: The argument, split. One box collects a paragraph that has to be
    #: re-read to find the case; two make a one-sided entry visible as one.
    pros: str | None = None
    concerns: str | None = None
    #: When the owner last recorded a judgement. Null until they do - saving a
    #: player is not reviewing them.
    last_reviewed_at: datetime | None = None
    added_at: datetime
    unavailable_reason: str | None = None


class ShortlistDetail(ShortlistOut):
    entries: list[ShortlistEntryOut]


class ComparedPlayer(BaseModel):
    """One column of a comparison."""

    player: PlayerSummary
    sample: SampleOut
    #: Where the owner has got to with this player. A comparison is read to
    #: make a decision, and three of the five columns having already been
    #: decided about is part of the answer.
    status: str
    status_label: str
    note: str | None
    pros: str | None = None
    concerns: str | None = None
    metrics: list[MetricOut]
    scores: list[ScoreOut]
    role: ScoreOut | None
    #: The same deterministic reading the profile page shows, per column.
    #:
    #: A comparison of five players is forty rows before it answers "what
    #: stands out about each of these", and that is the question it is opened
    #: to answer. Produced by the one reader the profile already uses rather
    #: than a second summariser, because two deterministic readings of one
    #: player would eventually disagree on two pages.
    interpretation: ScoutingInterpretationOut | None = None


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
    #: The refresh this check describes - a FootyStats generation, or an id
    #: the workflow minted for a Transfermarkt refresh - and whether it was a
    #: candidate in staging or is the dataset being served. Null on rows
    #: recorded before refreshes carried context.
    refresh_id: str | None = None
    generation_id: str | None = None
    context: Literal["CANDIDATE", "PUBLISHED"] | None = None


class CandidateChecksOut(BaseModel):
    """Checks that describe a refresh nobody is being served yet.

    A separate object rather than rows mixed into `checks`, because the page
    used to mix them: production serving G4, a G5 candidate checked and then
    failed at promotion, and every tick on the page describing G5. These say
    what they are about, and the published checks say what they are about,
    and a reader is never asked to tell them apart.
    """

    source: str
    refresh_id: str
    #: FootyStats only. Null for a provider with no generation model.
    generation_id: str | None = None
    executed_at: datetime
    checks: list[QualityCheckOut]


class PublishedChecksOut(BaseModel):
    """The checks that validated the dataset this source is serving."""

    source: str
    refresh_id: str | None = None
    generation_id: str | None = None
    published_at: datetime | None = None
    executed_at: datetime | None = None
    checks: list[QualityCheckOut]


class ProviderQualityOut(BaseModel):
    """One source, two datasets, kept apart: what is serving and what waits."""

    source: str
    published: PublishedChecksOut | None = None
    #: None when no refresh is between staging and production.
    candidate: CandidateChecksOut | None = None


class SourceFreshnessOut(BaseModel):
    """How current one source is, and how its last checks went.

    Three timestamps, answering three different questions, and the whole reason
    they are separate is that conflating any two of them produces a claim the
    data does not support:

      `last_checked_at`       when the automated checks last ran. They run
                              against whatever is serving, however old it is.
      `last_published_at`        when this source's data was last **published** -
                              the moment the figures on screen became these
                              figures.
      `last_load_attempt_at`  when a refresh last loaded this source into
                              staging, published or not.

    The middle one is the age of what a reader is looking at, and it is the
    only one that may be presented that way. A refresh that loads at 10:00 and
    fails its quality gate at 10:20 moves the third and not the second, because
    production is still yesterday's dataset and saying otherwise would be
    false in exactly the way somebody would act on.
    """

    source: str
    last_checked_at: datetime
    age_days: int
    checks_run: int
    failures: int
    warnings: int
    #: `None` for a source published before publications were recorded.
    last_published_at: datetime | None = None
    data_age_days: int | None = None
    rows_published: int | None = None
    #: Operational. A load attempt newer than `last_published_at` means a refresh
    #: is between staging and production - not that the data has changed.
    last_load_attempt_at: datetime | None = None


class VolumesOut(BaseModel):
    players: int
    competitions: int
    clubs: int
    player_seasons: int


class IdentityCoverageOut(BaseModel):
    """How much of the two sources has been reconciled into one identity.

    `unmatched` is not a failure. A player one source knows and the other does
    not is a player we know less about, and counting them stops the total
    implying a completeness nobody achieved.
    """

    players: int
    matched: int
    unmatched: int
    matched_share: float
    manual_overrides: int
    #: Matched on weaker evidence: plausible rather than settled, and where a
    #: wrong join would be if there is one.
    ambiguous: int


class AnalyticsFreshnessOut(BaseModel):
    """Whether the API is serving what the database currently holds."""

    players: int
    competitions: int
    built_at: datetime | None
    #: True when the database has moved since this view was built. Reporting it
    #: rather than rebuilding on a timer: a view that changes under a reader
    #: mid-session is worse than one that is briefly behind and says so.
    is_stale: bool


class RefreshGenerationOut(BaseModel):
    """Where the FootyStats refresh has got to.

    Operational, and deliberately dull: a generation id, a status, and counts.
    Nothing here names a storage path, a secret or a host - the question this
    answers is "why is the site still showing last week's figure", and that
    needs progress, not internals.
    """

    #: `20260907T040000Z`. A timestamp, and nothing else identifying.
    generation_id: str
    #: IN_PROGRESS | COMPLETE | VALIDATED | PUBLISHED | FAILED.
    status: str
    created_at: str | None = None
    last_updated_at: str | None = None
    published_at: str | None = None

    total_expected_players: int = 0
    completed_players: int = 0
    failed_players: int = 0
    completion_pct: float = 0.0
    competitions_complete: int = 0
    competitions_expected: int = 0
    complete: bool = False


class RefreshStatusOut(BaseModel):
    """The published generation, and whatever is being fetched now."""

    #: Idle | In progress | Complete | Validating | Failed.
    state: str
    published: RefreshGenerationOut | None = None
    current: RefreshGenerationOut | None = None


class MetricAvailabilityOut(BaseModel):
    """A canonical metric the provider cannot supply, and what was found."""

    metric: str
    label: str
    #: Null when nothing was recorded. Absent evidence is stated as absent
    #: rather than filled with a plausible sentence.
    reason: str | None = None


class DerivedMetricOut(BaseModel):
    """A metric with no provider field, computed from ones that exist."""

    metric: str
    label: str
    #: The arithmetic, so the claim can be checked rather than believed.
    formula: str


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
    #: The most recent checks describing the dataset being served.
    checks: list[QualityCheckOut]
    #: The generation `checks` describe, when the publication ledger names one.
    published_generation_id: str | None = None
    #: Checks describing a refresh between staging and production, or one that
    #: failed to reach it. Never about the data on screen.
    candidate: list[CandidateChecksOut] = Field(default_factory=list)
    #: The same facts arranged per source: published beside candidate, which
    #: is how the page shows them.
    providers: list[ProviderQualityOut] = Field(default_factory=list)
    identity: IdentityCoverageOut | None = None
    #: Mean share of played minutes carrying detailed statistics, across every
    #: loaded player-season that has both figures. `None` when unmeasurable.
    average_detailed_coverage_pct: float | None = None
    #: Canonical metrics the configured provider cannot supply at all. Empty in
    #: demo mode, where everything is fabricated.
    unavailable_metrics: list[str] = Field(default_factory=list)
    #: The same metrics with the evidence that established each absence. A
    #: list of five names says nothing about whether a gap could ever close;
    #: "declared and null in all 691 sampled records" says it cannot.
    unavailable_detail: list[MetricAvailabilityOut] = Field(default_factory=list)
    #: Metrics the provider has no field for and the system computes anyway.
    #: Reported separately because they are the opposite fact, and were being
    #: reported as the same one.
    derived_metrics: list[DerivedMetricOut] = Field(default_factory=list)
    analytics: AnalyticsFreshnessOut | None = None
    #: FootyStats refresh progress. `None` when no generation exists yet,
    #: which is the normal state of a database loaded before generations.
    refresh: RefreshStatusOut | None = None
