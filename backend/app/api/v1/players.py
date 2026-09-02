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
    classify_coverage,
    detailed_coverage_pct,
)
from app.analytics.intelligence import IntelligenceScore
from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric
from app.analytics.percentiles import ComparisonContext, PercentileResult, PercentileScope
from app.analytics.roles import RoleScore
from app.analytics.sample import SAMPLE_BAND_COPY, SAMPLE_BAND_LABEL
from app.analytics.similarity import SimilarityFilters, SimilarityResult
from app.core.database import get_session_factory
from app.repositories.market_repository import market_value_history, transfers
from app.schemas.api import (
    ComparisonContextOut,
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
    ScoreOut,
    SimilarPlayerOut,
    SimilarPlayersResponse,
    TransferOut,
)
from app.services.analytics_service import AnalyticsView, PlayerRecord, get_analytics_view

router = APIRouter(prefix="/api/v1", tags=["players"])

#: Metrics shown on a profile, in reading order. Not every derived metric: a
#: profile that lists 43 numbers communicates less than one that lists 20.
PROFILE_METRICS: list[DerivedMetric] = [
    DerivedMetric.PROGRESSIVE_PASSES_PER90,
    DerivedMetric.COMPLETED_PASSES_PER90,
    DerivedMetric.PASS_COMPLETION,
    DerivedMetric.KEY_PASSES_PER90,
    DerivedMetric.XA_PER90,
    DerivedMetric.ACCURATE_CROSSES_PER90,
    DerivedMetric.SUCCESSFUL_DRIBBLES_PER90,
    DerivedMetric.DRIBBLE_SUCCESS_PERCENTAGE,
    DerivedMetric.TACKLES_PER90,
    DerivedMetric.SUCCESSFUL_TACKLES_PER90,
    DerivedMetric.INTERCEPTIONS_PER90,
    DerivedMetric.BLOCKS_PER90,
    DerivedMetric.CLEARANCES_PER90,
    DerivedMetric.DUEL_WIN_PERCENTAGE,
    DerivedMetric.AERIAL_DUEL_WIN_PERCENTAGE,
    DerivedMetric.SHOTS_PER90,
    DerivedMetric.NPXG_PER90,
    DerivedMetric.NON_PENALTY_GOALS_PER90,
    DerivedMetric.FOULS_DRAWN_PER90,
    DerivedMetric.DISPOSSESSED_PER90,
    DerivedMetric.SAVES_PER90,
    DerivedMetric.SAVE_PERCENTAGE,
    DerivedMetric.GOALS_CONCEDED_PER90,
]

_LABEL_OVERRIDES = {
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


def to_context(context: ComparisonContext) -> ComparisonContextOut:
    return ComparisonContextOut(
        scope=context.scope.value,
        position_group=context.position_group.value,
        season_id=context.season_id,
        competition_ids=list(context.competition_ids),
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
        best_role_score=best.score if best else None,
    )


def to_score(score: IntelligenceScore | RoleScore) -> ScoreOut:
    contributions = dict(score.contributions())
    return ScoreOut(
        key=score.key,
        label=score.label,
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
        caveat=score.caveat,
    )


def to_metric(result: PercentileResult) -> MetricOut:
    return MetricOut(
        metric=result.metric.value,
        label=metric_label(result.metric.value),
        value=result.value,
        percentile=result.percentile,
        lower_is_better=result.metric in LOWER_IS_BETTER,
        unavailable_reason=result.unavailable_reason,
    )


def to_similar(result: SimilarityResult, view: AnalyticsView) -> SimilarPlayerOut | None:
    record = view.get(result.candidate.player_key)
    if record is None:
        return None
    return SimilarPlayerOut(
        player=to_summary(record, view),
        similarity=result.similarity,
        shared_features=result.shared_features,
        profile_strength_ratio=result.profile_strength_ratio,
        comparable_strength=result.comparable_strength,
    )


def require_player(view: AnalyticsView, player_id: str) -> PlayerRecord:
    record = view.get(player_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return record


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def to_sample(record: PlayerRecord) -> SampleOut:
    """The evidence behind one player-season's figures.

    Built in one place because it used to be built in two - here and in the
    shortlist comparison - and two constructions of the same thing is how they
    stop agreeing. A reader comparing a player on their profile and on a
    shortlist must not be told two different things about the same season.
    """
    coverage = detailed_coverage_pct(record.stats.recorded_minutes, record.minutes)
    band = classify_coverage(coverage)
    return SampleOut(
        minutes=record.minutes,
        recorded_minutes=record.stats.recorded_minutes,
        detailed_coverage_pct=coverage,
        coverage_band=band.value if band else None,
        coverage_label=COVERAGE_BAND_LABEL[band] if band else None,
        coverage_explanation=COVERAGE_EXPLANATION if coverage is not None else None,
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
    metrics = [to_metric(ranked[m]) for m in PROFILE_METRICS if m in ranked]
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
            to_context(ranked[m].context)
            for m in PROFILE_METRICS
            if ranked.get(m) is not None and ranked[m].percentile is not None
        ),
        None,
    ) or next((to_context(ranked[m].context) for m in PROFILE_METRICS if m in ranked), None)
    scores = [to_score(s) for s in view.scores(player_id, scope=percentile_scope).values()]

    return PlayerStatsResponse(
        player_id=player_id,
        sample=to_sample(record),
        context=context,
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
    return RoleFitOut(
        best=to_score(fit.best) if fit.best else None,
        alternatives=[to_score(s) for s in fit.alternatives],
        meaning=fit.meaning,
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

    return PlayerProfileResponse(
        player=get_player(player_id),
        stats=get_player_stats(player_id, scope=PercentileScope.COMPETITION.value),
        roles=roles,
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
