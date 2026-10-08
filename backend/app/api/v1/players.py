"""Player endpoints.

Returns results, never implementations: no weights, no formulas, no provider
field names reach the client (spec section 28). Scores do carry their component
percentiles, because a ranking that cannot be interrogated is not usable by a
recruitment department — but the definition that produced them stays here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.analytics.contracts import expires_within
from app.analytics.coverage import (
    COVERAGE_BAND_LABEL,
    COVERAGE_EXPLANATION,
    MINUTES_DISCREPANCY_EXPLANATION,
    MINUTES_DISCREPANCY_LABEL,
    classify_coverage,
    coverage_display_pct,
    detailed_coverage_pct,
    minutes_are_inconsistent,
)
from app.analytics.intelligence import IntelligenceScore, ScoreDefinition
from app.analytics.interpretation import (
    NOT_CAPTURED,
    MetricReading,
    RoleReading,
    ScoreReading,
    interpret,
)
from app.analytics.metrics import LOWER_IS_BETTER, METRIC_FAMILIES, DerivedMetric
from app.analytics.percentiles import ComparisonContext, PercentileResult, PercentileScope
from app.analytics.roles import SECONDARY_COVERAGE_FLOOR, RoleConfigError, RoleScore
from app.analytics.sample import SAMPLE_BAND_COPY, SAMPLE_BAND_LABEL
from app.analytics.similarity import FeatureComparison, SimilarityFilters, SimilarityResult
from app.core.database import get_session_factory
from app.repositories.market_repository import market_value_history, transfers
from app.schemas.api import (
    ComparisonContextOut,
    CoreDimensionOut,
    FeatureComparisonOut,
    FindingOut,
    MarketValuePointOut,
    MetricOut,
    PlayerDetail,
    PlayerListResponse,
    PlayerProfileResponse,
    PlayerStatsResponse,
    PlayerSummary,
    RoleFitOut,
    SampleOut,
    ScoreComponentOut,
    ScoreEvidenceOut,
    ScoreOut,
    ScoutingInterpretationOut,
    SimilarPlayerOut,
    SimilarPlayersResponse,
    TransferOut,
    UnscoredRoleOut,
)
from app.schemas.canonical import PlayerSeasonStats, position_group_name
from app.services.analytics_service import AnalyticsView, PlayerRecord, get_analytics_view

router = APIRouter(prefix="/api/v1", tags=["players"])

#: Metrics shown on a profile, in reading order. Not every derived metric: a
#: profile that lists 43 numbers communicates less than one that lists 20.
#: Every metric a profile shows, in reading order.
#:
#: THE RULE THIS LIST HAS TO KEEP
#:
#: Everything a role is scored from appears here. The whole claim of the role
#: breakdown is that a reader can check it, and for six metrics they could
#: not: a validation audit found 40% of the Poacher score - shots on target,
#: shot conversion and shot quality - contributing to a number while appearing
#: nowhere on the player's page. Dribbled past carried 20% of the Defensive
#: Full-Back score and 32% of its realised contribution for one player, and
#: was equally invisible.
#:
#: Hand-written lists drift. `test_every_role_metric_is_inspectable` compares
#: this against the role configuration and fails if a role ever reaches for a
#: metric the profile does not print, so the rule is enforced rather than
#: remembered.
#:
#: Grouped the way `METRIC_FAMILIES` groups them, because the comparison draws
#: a heading wherever the family changes and a metric out of place would split
#: its family into two sections with the same name.
PROFILE_METRICS: list[DerivedMetric] = [
    # -- Passing --
    DerivedMetric.PROGRESSIVE_PASSES_PER90,
    DerivedMetric.COMPLETED_PASSES_PER90,
    DerivedMetric.PASS_COMPLETION,
    # -- Creation --
    DerivedMetric.KEY_PASSES_PER90,
    DerivedMetric.ACCURATE_CROSSES_PER90,
    # -- Dribbling --
    DerivedMetric.SUCCESSFUL_DRIBBLES_PER90,
    DerivedMetric.DRIBBLE_SUCCESS_PERCENTAGE,
    # -- Defending --
    DerivedMetric.TACKLES_PER90,
    DerivedMetric.SUCCESSFUL_TACKLES_PER90,
    DerivedMetric.INTERCEPTIONS_PER90,
    DerivedMetric.BLOCKS_PER90,
    DerivedMetric.CLEARANCES_PER90,
    # -- Duels --
    DerivedMetric.DUEL_WIN_PERCENTAGE,
    DerivedMetric.AERIAL_DUEL_WIN_PERCENTAGE,
    # 20% of the Target Forward role, previously invisible.
    DerivedMetric.AERIAL_DUELS_WON_PER90,
    # -- Shooting --
    DerivedMetric.SHOTS_PER90,
    # These three made up 40% of the Poacher score and appeared nowhere.
    DerivedMetric.SHOTS_ON_TARGET_PER90,
    DerivedMetric.SHOT_CONVERSION,
    DerivedMetric.SHOT_QUALITY,
    # -- Goal threat --
    DerivedMetric.XA_PER90,
    DerivedMetric.NPXG_PER90,
    DerivedMetric.NON_PENALTY_GOALS_PER90,
    # -- Discipline and ball security --
    DerivedMetric.FOULS_DRAWN_PER90,
    DerivedMetric.DISPOSSESSED_PER90,
    # 20% of the Defensive Full-Back role, and 32% of one audited player's
    # realised score. Previously invisible.
    DerivedMetric.DRIBBLED_PAST_PER90,
    # -- Goalkeeping --
    DerivedMetric.SAVES_PER90,
    # 20% of the Shot Stopper role, previously invisible.
    DerivedMetric.INSIDE_BOX_SAVES_PER90,
    DerivedMetric.SAVE_PERCENTAGE,
    DerivedMetric.GOALS_CONCEDED_PER90,
]


_LABEL_OVERRIDES = {
    # Tackle *attempts*. The provider declares a successful-tackles field and
    # never populates it, so what we have is how often a player engages, not
    # how often they win the ball. "Tackles /90" reads as the second to most
    # people, and a label that implies a measurement we do not have is worse
    # than a longer one.
    "tackles_per90": "Tackles attempted /90",
    "successful_tackles_per90": "Tackles won /90",
    "tackle_success_percentage": "Tackle success %",
    "npxg_per90": "npxG /90",
    "xa_per90": "xA /90",
    "xg_per90": "xG /90",
    "pass_completion": "Pass completion %",
    "shot_accuracy": "Shot accuracy %",
    "shot_conversion": "Shot conversion %",
    "save_percentage": "Save %",
}


def metric_label(name: str) -> str:
    """Human label for a metric key."""
    if name in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[name]
    if name.startswith("score:"):
        return name.removeprefix("score:").replace("_", " ").title()
    label = name.replace("_per90", " /90").replace("_percentage", " %").replace("_", " ")
    return label[:1].upper() + label[1:]


def to_context(
    context: ComparisonContext, view: AnalyticsView | None = None
) -> ComparisonContextOut:
    """Serialise a comparison population, in words a reader can use.

    The ids stay - callers key on them - but nothing forces a reader to. A
    profile used to say `CM · footystats:12345 · 2026/27`, which names the
    right population in a vocabulary belonging to the model and the provider,
    neither of which the reader has.

    `view` supplies competition display names. Optional so existing callers
    keep working; without it the ids come back as their own names, which is
    honest rather than pretty.
    """
    ids = list(context.competition_ids)
    names = [
        (view.competitions.get(competition_id) if view else None) or competition_id
        for competition_id in ids
    ]
    return ComparisonContextOut(
        competitions_in_population=context.competitions_in_population,
        competitions_established=context.competitions_established,
        established_share=context.established_share,
        median_minutes=context.median_minutes,
        maturity_note=context.maturity_note,
        is_early_season=context.is_early_season,
        scope=context.scope.value,
        position_group=context.position_group.value,
        position_label=position_group_name(context.position_group),
        season_id=context.season_id,
        competition_ids=ids,
        competition_names=names,
        population_size=context.population_size,
        minimum_minutes=context.minimum_minutes,
        label=context.label,
        caveat=context.caveat,
        strength_adjusted=context.strength_adjusted,
    )


def to_summary(record: PlayerRecord, view: AnalyticsView) -> PlayerSummary:
    fit = view.best_roles.get(record.player_key)
    best = fit.best if fit else None
    return PlayerSummary(
        player_id=record.player_key,
        name=record.full_name,
        age=record.age,
        position_group=record.position_group.value,
        raw_position=record.raw_position,
        club=record.club_name,
        competition=record.competition_name,
        nationality=record.nationality,
        minutes=record.minutes,
        sample_band=record.sample_band.value,
        market_value_eur=record.market_value_eur,
        contract_expires=record.contract_expires,
        best_role=best.label if best else None,
        best_role_key=best.key if best else None,
        best_role_score=best.score if best else None,
        best_role_percentile=best.role_fit_percentile if best else None,
    )


#: Share of a realised score above which one component is worth naming.
#:
#: A judgement, and a loose one. Below it, a leading component is ordinary -
#: something has to be largest. Above it the role is behaving like a ranking
#: of one metric, which a reader comparing two players on the same role name
#: cannot see from the number.
DOMINANT_CONTRIBUTION = 40.0


def _dominant(score: IntelligenceScore | RoleScore) -> tuple[str | None, float | None]:
    """The component carrying an outsized share of what the score came out as.

    Realised contribution, not configured weight. The two diverge: a 30%
    component on a percentile of 95 contributes more than a 40% one on a
    percentile of 20, and it is the first that a reader is unknowingly ranking
    by.
    """
    contributions = {m: c for m, c in score.contributions() if c is not None}
    total = sum(contributions.values())
    if not contributions or total <= 0:
        return None, None
    metric = max(contributions, key=lambda m: contributions[m])
    share = contributions[metric] / total * 100.0
    if share < DOMINANT_CONTRIBUTION:
        return None, None
    return metric_label(metric), share


def to_score(
    score: IntelligenceScore | RoleScore,
    stats: PlayerSeasonStats | None = None,
    definitions: dict[str, ScoreDefinition] | None = None,
) -> ScoreOut:
    contributions = dict(score.contributions())
    dominant = _dominant(score)
    return ScoreOut(
        key=score.key,
        label=score.label,
        # Roles carry no description of their own; the role's caveat and its
        # components do that work. `getattr` keeps one serialiser for both.
        description=getattr(score, "description", None),
        score=score.score,
        coverage=score.coverage,
        components=[
            ScoreComponentOut(
                metric=component.metric,
                label=metric_label(component.metric),
                weight=component.weight,
                percentile=component.value,
                contribution=contributions.get(component.metric),
            )
            for component in score.components
        ],
        missing=[metric_label(m) for m in score.missing],
        validity=getattr(score, "validity", None),
        core_dimensions=[
            CoreDimensionOut(
                name=d.name,
                satisfied=d.satisfied,
                available=[metric_label(m) for m in d.available],
                missing=[metric_label(m) for m in d.missing],
            )
            for d in getattr(score, "core_dimensions", ())
        ],
        role_fit_percentile_reason=getattr(score, "role_fit_percentile_reason", None),
        dominant_component=dominant[0],
        dominant_share=dominant[1],
        evidence=_score_evidence(score.key, stats, definitions),
        caveat=score.caveat,
        # Roles only; intelligence scores carry neither. `getattr` keeps one
        # serialiser for both rather than two that can disagree.
        availability_note=getattr(score, "availability_note", None),
        explanation=getattr(score, "explanation", None),
        # Roles carry a standing within their own distribution; intelligence
        # scores do not, and getattr keeps one serialiser for both rather than
        # two that can disagree.
        role_fit_percentile=getattr(score, "role_fit_percentile", None),
        role_population=getattr(score, "role_population", 0),
        # Roles only, same reasoning as above: intelligence scores carry
        # coverage but are not banded, and one serialiser beats two that can
        # disagree.
        coverage_band=(
            band.value if (band := getattr(score, "coverage_band", None)) is not None else None
        ),
        coverage_label=getattr(score, "coverage_label", None),
        is_limited=bool(getattr(score, "is_limited", False)),
    )


def to_metric(result: PercentileResult, wider: PercentileResult | None = None) -> MetricOut:
    return MetricOut(
        metric=result.metric.value,
        label=metric_label(result.metric.value),
        value=result.value,
        percentile=result.percentile,
        performance_percentile=result.oriented,
        global_percentile=wider.percentile if wider is not None else None,
        global_performance_percentile=wider.oriented if wider is not None else None,
        lower_is_better=result.metric in LOWER_IS_BETTER,
        family=METRIC_FAMILIES.get(result.metric),
        unavailable_reason=result.unavailable_reason,
    )


def _score_evidence(
    key: str,
    stats: PlayerSeasonStats | None,
    definitions: dict[str, ScoreDefinition] | None,
) -> ScoreEvidenceOut | None:
    """The event count behind a rate-built score, read from the raw stats.

    Derived from the configuration rather than from a list here, so adding an
    `evidence` block to a score in `intelligence_scores.yaml` is all it takes
    and nothing in this file has to know which scores are rate-built.
    """
    if stats is None or definitions is None:
        return None
    definition = definitions.get(key)
    if definition is None or definition.evidence is None:
        return None
    count = getattr(stats, definition.evidence.metric, None)
    if not isinstance(count, int):
        # The provider did not supply the count. Absent, not zero: claiming
        # nought events would be a measurement nobody made.
        return None
    low = count < definition.evidence.headline_threshold
    noun = _count_noun(definition.evidence.noun, count)
    return ScoreEvidenceOut(
        events=count,
        noun=definition.evidence.noun,
        threshold=definition.evidence.headline_threshold,
        low=low,
        label=(f"Low evidence - {count:,} {noun}" if low else f"{count:,} {noun}"),
    )


def _count_noun(noun: str, count: int) -> str:
    """ "1 dribble attempted", not "1 dribbles attempted".

    The configured nouns are plural because they are almost always read that
    way, and the one count that needs the singular is the one most worth
    printing. Drops the trailing "s" from the head word, which covers "shots"
    and "dribbles attempted"; an irregular noun would need its own field, and
    none has turned up yet.
    """
    if count != 1:
        return noun
    head, _, tail = noun.partition(" ")
    singular = head[:-1] if head.endswith("s") else head
    return f"{singular} {tail}".strip()


def _interpret(
    player: PlayerDetail, stats: PlayerStatsResponse, roles: RoleFitOut | None
) -> ScoutingInterpretationOut | None:
    """Read the profile that was just assembled."""
    return read_profile(
        best_role=roles.best if roles is not None else None,
        alternatives=[a.label for a in roles.alternatives[:3]] if roles is not None else [],
        scores=stats.scores,
        metrics=stats.metrics,
        sample=stats.sample,
        position_label=player.position_group,
    )


def read_profile(
    *,
    best_role: ScoreOut | None,
    alternatives: list[str],
    scores: list[ScoreOut],
    metrics: list[MetricOut],
    sample: SampleOut,
    position_label: str | None,
) -> ScoutingInterpretationOut | None:
    """Read a profile from the pieces a response already carries.

    Built from the response objects rather than from the view, so the prose
    cannot describe a number the page does not show: if a metric was withheld
    for want of a population, the reading has no access to it either.

    Shared with the comparison, which assembles the same pieces per column and
    would otherwise need its own summariser - and two deterministic readers of
    one profile is one too many, because they would eventually disagree about
    the same player on two pages.
    """
    role_reading = None
    if best_role is not None:
        best = best_role
        role_reading = RoleReading(
            label=best.label,
            score=best.score,
            percentile=best.role_fit_percentile,
            coverage=best.coverage,
            is_limited=best.is_limited,
            missing=tuple(best.missing),
            alternatives=tuple(alternatives),
            components=tuple(c.label for c in best.components),
        )

    reading = interpret(
        role=role_reading,
        scores=[
            ScoreReading(
                s.label,
                s.score,
                s.coverage,
                low_evidence=bool(s.evidence and s.evidence.low),
                evidence_label=s.evidence.label if s.evidence else None,
            )
            for s in scores
        ],
        metrics=[
            MetricReading(m.label, m.percentile, m.lower_is_better, m.unavailable_reason, m.metric)
            for m in metrics
        ],
        minutes=sample.minutes,
        sample_band_label=sample.band_label,
        detailed_coverage_pct=sample.detailed_coverage_pct,
        position_label=position_label,
    )
    if reading.is_empty:
        return None

    return ScoutingInterpretationOut(
        profile=reading.profile,
        strengths=[
            FindingOut(label=f.label, percentile=f.percentile, reading=f.reading)
            for f in reading.strengths
        ],
        watch_outs=[
            FindingOut(label=f.label, percentile=f.percentile, reading=f.reading)
            for f in reading.watch_outs
        ],
        unavailable=reading.unavailable,
        confidence=reading.confidence,
        not_captured=list(NOT_CAPTURED),
    )


def to_similar(result: SimilarityResult, view: AnalyticsView) -> SimilarPlayerOut | None:
    record = view.get(result.candidate.player_key)
    if record is None:
        return None
    return SimilarPlayerOut(
        player=to_summary(record, view),
        similarity=result.similarity,
        shared_features=result.shared_features,
        expected_features=result.expected_features,
        feature_coverage_pct=result.feature_coverage * 100.0,
        coverage_band=result.coverage_band.value,
        coverage_label=result.coverage_label,
        ranking_similarity=result.ranking.ranked if result.ranking else result.similarity,
        evidence_weight=result.ranking.weight if result.ranking else 1.0,
        ranking_note=(
            result.ranking.explain(minutes=result.candidate_minutes, noun="similarity")
            if result.ranking
            else None
        ),
        profile_strength_ratio=result.profile_strength_ratio,
        comparable_strength=result.comparable_strength,
        drivers=[_to_feature(f) for f in result.drivers()],
        differences=[_to_feature(f) for f in result.differences()],
    )


def _to_feature(feature: FeatureComparison) -> FeatureComparisonOut:
    return FeatureComparisonOut(
        metric=feature.metric.value,
        label=metric_label(feature.metric.value),
        gap=feature.gap,
        target=feature.target,
        candidate=feature.candidate,
    )


def require_player(view: AnalyticsView, player_id: str) -> PlayerRecord:
    record = view.get(player_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return record


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def to_sample(record: PlayerRecord, view: AnalyticsView | None = None) -> SampleOut:
    """The evidence behind one player-season's figures.

    Built in one place because it used to be built in two - here and in the
    shortlist comparison - and two constructions of the same thing is how they
    stop agreeing. A reader comparing a player on their profile and on a
    shortlist must not be told two different things about the same season.
    """
    raw = detailed_coverage_pct(record.stats.recorded_minutes, record.minutes)
    coverage = coverage_display_pct(raw)
    inconsistent = minutes_are_inconsistent(record.stats.recorded_minutes, record.minutes)
    # Banded on the displayed figure, so a capped 100% reads as excellent
    # rather than falling through a comparison it was never meant to fail.
    band = classify_coverage(coverage)

    # A third measure, and the reason it exists: a profile can carry
    # "Established Sample" and "100% detailed coverage" and still be missing
    # half of its metrics. Minutes played and the share of those minutes the
    # provider described in detail say nothing about how many of the profile's
    # figures could actually be computed. The denominator comes from the
    # population - what a player in this position group is seen to carry -
    # because counting goalkeeping metrics against a full-back would report
    # every outfield profile as incomplete.
    available_count: int | None = None
    expected_count: int | None = None
    metric_coverage: float | None = None
    if view is not None:
        applicable = view.applicable_metrics(record.position_group)
        expected = [m for m in PROFILE_METRICS if m in applicable]
        if expected:
            carried = record.metrics.available()
            available_count = len([m for m in expected if m in carried])
            expected_count = len(expected)
            metric_coverage = available_count / expected_count * 100.0

    return SampleOut(
        minutes=record.minutes,
        recorded_minutes=record.stats.recorded_minutes,
        detailed_coverage_pct=coverage,
        detailed_coverage_raw_pct=raw,
        provider_minutes_inconsistent=inconsistent,
        minutes_discrepancy_label=MINUTES_DISCREPANCY_LABEL if inconsistent else None,
        minutes_discrepancy_explanation=(MINUTES_DISCREPANCY_EXPLANATION if inconsistent else None),
        coverage_band=band.value if band else None,
        coverage_label=COVERAGE_BAND_LABEL[band] if band else None,
        coverage_explanation=COVERAGE_EXPLANATION if coverage is not None else None,
        metric_coverage_pct=metric_coverage,
        metrics_available=available_count,
        metrics_expected=expected_count,
        band=record.sample_band.value,
        band_label=SAMPLE_BAND_LABEL[record.sample_band],
        explanation=SAMPLE_BAND_COPY[record.sample_band],
    )


@router.get("/players", response_model=PlayerListResponse)
def list_players(
    search: str | None = Query(default=None, max_length=100),
    position_group: str | None = None,
    competition: str | None = None,
    club: str | None = None,
    nationality: str | None = None,
    foot: str | None = None,
    role: str | None = None,
    age_min: int | None = Query(default=None, ge=14, le=50),
    age_max: int | None = Query(default=None, ge=14, le=50),
    minutes_min: int | None = Query(default=None, ge=0),
    #: Confidence band, not eligibility. It sits beside `minutes_min` rather
    #: than replacing it because the two answer different questions: "at least
    #: this much football" and "this much and no more". Asking for the very
    #: low band is how somebody looks for emerging players, which a minimum
    #: alone cannot express. Default is every band, and nothing is excluded
    #: unless the reader asks.
    sample_band: str | None = Query(default=None),
    market_value_min: int | None = Query(default=None, ge=0),
    market_value_max: int | None = Query(default=None, ge=0),
    height_min: int | None = Query(default=None, ge=140, le=220),
    contract_within_months: int | None = Query(default=None, ge=0, le=120),
    sort: str = Query(default="minutes"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> PlayerListResponse:
    """Search the player database.

    Paginated deliberately (section 27): the browser never receives the whole
    database to filter client-side.
    """
    view = get_analytics_view()
    needle = search.strip().lower() if search else None

    def matches(record: PlayerRecord) -> bool:
        if needle and needle not in record.full_name.lower():
            return False
        if position_group and record.position_group.value != position_group:
            return False
        if competition and record.competition_id != competition:
            return False
        if club and record.club_id != club:
            return False
        if nationality and record.nationality != nationality:
            return False
        if foot and (record.preferred_foot.value if record.preferred_foot else None) != foot:
            return False
        if age_min is not None and (record.age is None or record.age < age_min):
            return False
        if age_max is not None and (record.age is None or record.age > age_max):
            return False
        if minutes_min is not None and (record.minutes or 0) < minutes_min:
            return False
        if sample_band is not None and record.sample_band.value != sample_band:
            return False
        if height_min is not None and (record.height_cm or 0) < height_min:
            return False
        if market_value_min is not None and (record.market_value_eur or 0) < market_value_min:
            return False
        if (
            market_value_max is not None
            and record.market_value_eur is not None
            and record.market_value_eur > market_value_max
        ):
            return False
        if contract_within_months is not None and not expires_within(
            record.contract_expires, contract_within_months
        ):
            return False
        if role:
            fit = view.best_roles.get(record.player_key)
            if not fit or not fit.best or fit.best.key != role:
                return False
        return True

    found = [r for r in view.players.values() if matches(r)]

    def sort_key(record: PlayerRecord) -> tuple:
        fit = view.best_roles.get(record.player_key)
        best = (fit.best.score if fit and fit.best else 0.0) or 0.0
        if sort == "name":
            return (record.full_name.lower(),)
        if sort == "age":
            return (record.age or 999,)
        if sort == "market_value":
            return (-(record.market_value_eur or 0),)
        if sort == "role_score":
            return (-best,)
        return (-(record.minutes or 0),)

    found.sort(key=sort_key)
    page = found[offset : offset + limit]
    return PlayerListResponse(
        items=[to_summary(r, view) for r in page],
        total=len(found),
        offset=offset,
        limit=limit,
        is_mock=view.is_mock,
    )


@router.get("/players/{player_id}", response_model=PlayerDetail)
def get_player(player_id: str) -> PlayerDetail:
    view = get_analytics_view()
    record = require_player(view, player_id)
    summary = to_summary(record, view)
    return PlayerDetail(
        **summary.model_dump(),
        preferred_foot=record.preferred_foot.value if record.preferred_foot else None,
        height_cm=record.height_cm,
        date_of_birth=record.date_of_birth,
        is_mock=view.is_mock,
    )


@router.get("/players/{player_id}/stats", response_model=PlayerStatsResponse)
def get_player_stats(
    player_id: str, scope: str = Query(default="competition")
) -> PlayerStatsResponse:
    """Per-90 metrics with contextual percentiles, and intelligence scores."""
    view = get_analytics_view()
    record = require_player(view, player_id)
    try:
        percentile_scope = PercentileScope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unknown comparison scope") from exc

    ranked = view.rank(player_id, PROFILE_METRICS, scope=percentile_scope)

    # The same metrics against every loaded competition, so a domestic rank can
    # be read beside the one it looks like from outside. Only when the asked-for
    # scope is domestic: against the global population they would be the same
    # number twice, which reads as corroboration and is not.
    wider = (
        view.rank(player_id, PROFILE_METRICS, scope=PercentileScope.GLOBAL)
        if percentile_scope is PercentileScope.COMPETITION
        else {}
    )
    metrics = [to_metric(ranked[m], wider.get(m)) for m in PROFILE_METRICS if m in ranked]
    # Metrics that do not apply to the position carry no value at all; showing
    # a row of blanks for every goalkeeping stat on an outfield profile is noise.
    metrics = [m for m in metrics if m.value is not None]

    # The context of a metric that was actually ranked, not simply the first in
    # the list. Population size is per metric - it counts the players carrying a
    # value for it - so taking the first unconditionally reported the comparison
    # group of a metric the provider does not supply, and a profile showing
    # sixteen percentiles announced that they were measured against nobody.
    # Every metric absent is a truthful zero; sixteen present is not.
    context = next(
        (
            to_context(ranked[m].context, view)
            for m in PROFILE_METRICS
            if ranked.get(m) is not None and ranked[m].percentile is not None
        ),
        None,
    ) or next((to_context(ranked[m].context, view) for m in PROFILE_METRICS if m in ranked), None)
    global_context = next(
        (
            to_context(wider[m].context, view)
            for m in PROFILE_METRICS
            if wider.get(m) is not None and wider[m].percentile is not None
        ),
        None,
    )
    definitions = view.intelligence.definitions if view.intelligence else None
    scores = [
        to_score(s, record.stats, definitions)
        for s in view.scores(player_id, scope=percentile_scope).values()
    ]

    return PlayerStatsResponse(
        player_id=player_id,
        sample=to_sample(record, view),
        context=context,
        global_context=global_context,
        metrics=metrics,
        scores=scores,
    )


@router.get("/players/{player_id}/roles", response_model=RoleFitOut)
def get_player_roles(player_id: str) -> RoleFitOut:
    view = get_analytics_view()
    require_player(view, player_id)
    fit = view.role_fit(player_id)
    if fit is None:
        raise HTTPException(status_code=404, detail="No role fit available")
    unscored = [] if fit.best else _unscored_roles(view, player_id)
    return RoleFitOut(
        best=to_score(fit.best) if fit.best else None,
        alternatives=[to_score(s) for s in fit.alternatives],
        partial_evidence=[to_score(s) for s in fit.partial_evidence],
        unscored=unscored,
        unscored_reason=_why_no_role(unscored) if not fit.best else None,
        meaning=fit.meaning,
    )


def _unscored_roles(view: AnalyticsView, player_id: str) -> list[UnscoredRoleOut]:
    """Every role this position could have been measured for, and the shortfall.

    Read back from the engine rather than described: each role is scored, and
    the ones that came back without a number report the coverage they reached
    against the minimum they are configured to need. Nothing here is a
    constant, so a change to a role's definition changes this page too.
    """
    metrics = view.player_metrics(player_id)
    if metrics is None or view.roles is None:
        return []
    shortfalls: list[UnscoredRoleOut] = []
    for key, role in view.roles.roles.items():
        if not role.applies_to(metrics.position_group):
            continue
        try:
            result = view.roles.score(metrics, key)
        except RoleConfigError:
            continue
        if result.score is not None:
            continue
        shortfalls.append(
            UnscoredRoleOut(
                key=key,
                label=role.label,
                coverage_pct=result.coverage * 100.0,
                required_pct=SECONDARY_COVERAGE_FLOOR * 100.0,
                missing=[metric_label(m) for m in result.missing],
            )
        )
    # Closest first: the role that came nearest is the one worth naming.
    shortfalls.sort(key=lambda r: r.required_pct - r.coverage_pct)
    return shortfalls


def _why_no_role(unscored: list[UnscoredRoleOut]) -> str:
    """The sentence that replaces "No role fit could be computed."."""
    if not unscored:
        return (
            "No role is defined for this position group, so there is nothing to "
            "score this profile against."
        )
    closest = unscored[0]
    return (
        f"No role reached the metric coverage it requires. The closest was "
        f"{closest.label}, which was measurable to {closest.coverage_pct:.0f}% "
        f"of its definition against the {closest.required_pct:.0f}% it needs. "
        f"The player is unchanged and every metric they do carry is below; what "
        f"is missing is provider data, not performance."
    )


@router.get("/players/{player_id}/similar", response_model=SimilarPlayersResponse)
def get_similar_players(
    player_id: str,
    limit: int = Query(default=15, ge=1, le=50),
    age_max: int | None = Query(default=None, ge=14, le=50),
    age_min: int | None = Query(default=None, ge=14, le=50),
    market_value_max: int | None = Query(default=None, ge=0),
    different_competition: bool = False,
    exclude_same_club: bool = False,
    younger_only: bool = False,
    contract_within_months: int | None = Query(default=None, ge=0, le=120),
    # No floor. A caller who wants one passes it.
    minutes_min: int = Query(default=0, ge=0),
) -> SimilarPlayersResponse:
    from app.analytics.similarity import SIMILARITY_MEANING

    view = get_analytics_view()
    record = require_player(view, player_id)

    filters = SimilarityFilters(
        min_age=age_min,
        max_age=age_max,
        max_market_value_eur=market_value_max,
        different_competition_only=different_competition,
        exclude_same_club=exclude_same_club,
        younger_than_target=younger_only,
        contract_expiring_within_months=contract_within_months,
    )
    results = view.similar(player_id, filters=filters, limit=limit, minimum_minutes=minutes_min)
    mapped = [out for r in results if (out := to_similar(r, view)) is not None]

    return SimilarPlayersResponse(
        target=to_summary(record, view),
        results=mapped,
        meaning=SIMILARITY_MEANING,
    )


@router.get("/players/{player_id}/profile", response_model=PlayerProfileResponse)
def get_player_profile(
    player_id: str,
    similar_limit: int = Query(default=6, ge=1, le=50),
) -> PlayerProfileResponse:
    """The whole profile page in one request.

    Exists for the deploy that renders every profile ahead of time. Four
    requests a page across five and a half thousand players is twenty-two
    thousand round trips, which the rate limit refuses and should refuse; one a
    page is four minutes of work.

    It calls the same functions the four endpoints are, with every default
    stated rather than inherited - a `Query(...)` default is a marker object,
    not a value, and reaches the body as itself when a handler is called
    directly. `test_profile_matches_the_individual_endpoints` holds the two
    paths to the same answers.
    """
    view = get_analytics_view()
    require_player(view, player_id)

    try:
        roles: RoleFitOut | None = get_player_roles(player_id)
    except HTTPException as exc:
        # A player with no fitted role still has a profile worth showing. The
        # single-purpose endpoint answers 404 because there is nothing else for
        # it to say; here there is.
        if exc.status_code != 404:
            raise
        roles = None

    player = get_player(player_id)
    stats = get_player_stats(player_id, scope=PercentileScope.COMPETITION.value)

    return PlayerProfileResponse(
        player=player,
        stats=stats,
        roles=roles,
        interpretation=_interpret(player, stats, roles),
        # Read from the database like everything else, so the page cannot
        # disagree with itself about a player.
        market_value_history=get_market_value_history(player_id),
        transfers=get_transfers(player_id),
        similar=get_similar_players(
            player_id,
            limit=similar_limit,
            age_max=None,
            age_min=None,
            market_value_max=None,
            different_competition=False,
            exclude_same_club=False,
            younger_only=False,
            contract_within_months=None,
            minutes_min=0,
        ),
    )


@router.get("/players/{player_id}/market-value", response_model=list[MarketValuePointOut])
def get_market_value_history(player_id: str) -> list[MarketValuePointOut]:
    """Valuation history, read from what the pipeline loaded.

    Not from the market provider: in demo mode that is the mock one, which knows
    only invented ids and returned nothing for real players, and in production
    it reads the Transfermarkt snapshot directly, so the page could disagree
    with the database the rest of it comes from.
    """
    view = get_analytics_view()
    require_player(view, player_id)
    with get_session_factory()() as session:
        return [
            MarketValuePointOut(valued_on=p.valued_on, market_value_eur=p.market_value_eur)
            for p in market_value_history(session, player_id)
        ]


@router.get("/players/{player_id}/transfers", response_model=list[TransferOut])
def get_transfers(player_id: str) -> list[TransferOut]:
    view = get_analytics_view()
    require_player(view, player_id)
    with get_session_factory()() as session:
        return [
            TransferOut(
                transfer_date=t.transfer_date,
                season=t.season,
                from_club=t.from_club,
                to_club=t.to_club,
                fee_eur=t.fee_eur,
                transfer_type=t.transfer_type,
            )
            for t in transfers(session, player_id)
        ]
