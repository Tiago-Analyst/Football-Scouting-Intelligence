"""Recruitment, replacement and market opportunity endpoints.

All three rank players, and all three must explain why. A shortlist a
recruitment department cannot interrogate is not usable, so every candidate
carries the component percentiles or the reasons that placed it there.

None of the weightings a user supplies leave the server, and none of the
underlying definitions do either (spec section 28).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.analytics.intelligence import ScoreDefinition
from app.analytics.percentiles import PercentileScope
from app.analytics.scoring import ScoreComponent, normalise_weights, weighted_score
from app.analytics.similarity import SimilarityFilters
from app.api.v1.players import metric_label, require_player, to_summary
from app.schemas.api import (
    OpportunitiesResponse,
    OpportunityOut,
    RecruitmentCandidate,
    RecruitmentFilters,
    RecruitmentRequest,
    RecruitmentResponse,
    ReplacementCandidate,
    ReplacementRequest,
    ReplacementResponse,
    ScoreComponentOut,
    UnavailableScoreOut,
)
from app.services.analytics_service import (
    REFERENCE_DATE,
    AnalyticsView,
    PlayerRecord,
    get_analytics_view,
)

router = APIRouter(prefix="/api/v1", tags=["recruitment"])

OPPORTUNITY_DISCLAIMER = (
    "These players meet the criteria you set. They are not identified as "
    "undervalued: no valuation model is applied, and market value is a "
    "crowd-sourced estimate rather than a transfer fee."
)

REPLACEMENT_MEANING = (
    "Replacement scores rank a statistical profile within the filters you set. "
    "They do not account for tactical system, role in the squad, personality or "
    "medical history, and are not a probability."
)

# Spec section 15.
SIMILARITY_WEIGHT = 0.55
ROLE_WEIGHT = 0.30
MARKET_WEIGHT = 0.15


def _passes_filters(record: PlayerRecord, filters: RecruitmentFilters) -> bool:
    """Apply squad and market constraints.

    A filter is skipped when the player does not carry the attribute it tests,
    except where absence genuinely cannot satisfy the condition. Dropping
    players for missing data would narrow results to whoever is best covered.
    """
    if filters.position_groups and record.position_group.value not in filters.position_groups:
        return False
    if filters.min_age is not None and (record.age is None or record.age < filters.min_age):
        return False
    if filters.max_age is not None and (record.age is None or record.age > filters.max_age):
        return False
    if (
        filters.max_market_value_eur is not None
        and record.market_value_eur is not None
        and record.market_value_eur > filters.max_market_value_eur
    ):
        return False
    if (
        filters.min_market_value_eur is not None
        and record.market_value_eur is not None
        and record.market_value_eur < filters.min_market_value_eur
    ):
        return False
    if filters.competitions and record.competition_id not in filters.competitions:
        return False
    if filters.nationalities and record.nationality not in filters.nationalities:
        return False
    if filters.preferred_foot:
        foot = record.preferred_foot.value if record.preferred_foot else None
        if foot != filters.preferred_foot:
            return False
    if filters.min_height_cm is not None and (record.height_cm or 0) < filters.min_height_cm:
        return False
    if filters.min_minutes is not None and (record.minutes or 0) < filters.min_minutes:
        return False
    if filters.contract_expiring_within_months is not None:
        if record.contract_expires is None:
            return False
        months = (record.contract_expires.year - REFERENCE_DATE.year) * 12 + (
            record.contract_expires.month - REFERENCE_DATE.month
        )
        if months > filters.contract_expiring_within_months:
            return False
    return True


@router.post("/recruitment/search", response_model=RecruitmentResponse)
def recruitment_search(request: RecruitmentRequest) -> RecruitmentResponse:
    """Rank players against a user-defined profile.

    The profile is a weighting across intelligence scores. Weights are
    normalised, so a profile adding to 99 shifts emphasis rather than rescaling
    every result.
    """
    view = get_analytics_view()
    if view.intelligence is None:
        raise HTTPException(status_code=503, detail="Analytics unavailable")

    known = set(view.intelligence.definitions)
    unknown = set(request.weights) - known
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown score(s): {', '.join(sorted(unknown))}"
        )
    positive = {k: v for k, v in request.weights.items() if v > 0}
    if not positive:
        raise HTTPException(status_code=422, detail="At least one positive weight is required")

    weights = normalise_weights(positive)
    # Scoring across competitions, so the caveat travels with the result.
    scope = PercentileScope.GLOBAL

    ranked: list[RecruitmentCandidate] = []
    caveat: str | None = None
    considered = 0
    #: How many candidates each requested score could actually be given, and
    #: what it was missing when it could not. A score available to nobody is the
    #: difference between "no player matched" and "this cannot be computed".
    available: dict[str, int] = dict.fromkeys(weights, 0)
    #: Components missing for *every* candidate that could not be given the
    #: score - the intersection, not one player's list. A component missing for
    #: one player is a thin comparison population; a component missing for all
    #: of them is one the provider does not supply, and only the second is worth
    #: telling someone they cannot fix.
    shortfall: dict[str, set[str] | None] = dict.fromkeys(weights, None)

    for record in view.players.values():
        if not _passes_filters(record, request.filters):
            continue
        considered += 1
        scores = view.scores(record.player_key, scope=scope)
        for key in weights:
            found = scores.get(key)
            if found is not None and found.score is not None:
                available[key] += 1
            elif found is not None:
                current = shortfall[key]
                missing = set(found.missing)
                shortfall[key] = missing if current is None else (current & missing)
        components = [
            ScoreComponent(
                metric=key,
                weight=weight * 100.0,
                value=scores[key].score if key in scores else None,
            )
            for key, weight in weights.items()
        ]
        result = weighted_score(components, min_coverage=1.0)
        if result.score is None:
            continue
        if caveat is None:
            first_score = next(iter(scores.values()), None)
            if first_score is not None:
                caveat = first_score.context.caveat

        contributions = dict(result.contributions())
        ranked.append(
            RecruitmentCandidate(
                player=to_summary(record, view),
                score=result.score,
                coverage=result.coverage,
                components=[
                    ScoreComponentOut(
                        metric=c.metric,
                        label=metric_label(c.metric),
                        weight=c.weight,
                        percentile=c.value,
                        contribution=contributions.get(c.metric),
                    )
                    for c in result.components
                ],
            )
        )

    ranked.sort(key=lambda c: c.score, reverse=True)
    page = ranked[request.offset : request.offset + request.limit]

    # Only meaningful once something was actually scored against: with no
    # candidate admitted, every score is trivially "unavailable", and saying so
    # would blame the data for filters that matched nobody.
    unavailable = (
        [
            UnavailableScoreOut(
                key=key,
                label=view.intelligence.definitions[key].label,
                missing=sorted(shortfall[key] or ()),
                reason=_why_unavailable(
                    view.intelligence.definitions[key], sorted(shortfall[key] or ())
                ),
            )
            for key, count in available.items()
            if count == 0
        ]
        if considered
        else []
    )

    return RecruitmentResponse(
        items=page,
        total=len(ranked),
        offset=request.offset,
        limit=request.limit,
        context_caveat=caveat,
        considered=considered,
        unavailable_scores=unavailable,
        explanation=_explain(considered, len(ranked), unavailable, weights),
    )


def _why_unavailable(definition: ScoreDefinition, missing: list[str]) -> str:
    """What stopped this score, in the words of the thing that stopped it."""
    if not missing:
        return f"{definition.label} could not be computed for any candidate in this search."
    names = ", ".join(metric_label(m) for m in sorted(missing))
    return (
        f"{definition.label} needs {names}, which the performance provider does not "
        f"supply. No amount of widening the filters will produce it."
    )


def _explain(
    considered: int,
    ranked: int,
    unavailable: list[UnavailableScoreOut],
    weights: dict[str, float],
) -> str | None:
    """Say why the result is empty or short, when it is.

    A profile is scored only when every requested component is present, because
    a score built from a subset is not comparable with one built from the whole.
    That is the right rule and an invisible one: it turns "this metric does not
    exist" into an empty page that looks exactly like filters set too narrow.
    """
    if ranked:
        if unavailable:
            return (
                f"{len(unavailable)} of the {len(weights)} requested scores could not be "
                "produced, so this ranking uses the rest."
            )
        return None

    if considered == 0:
        # Checked before the data is blamed: no candidate was admitted, so
        # nothing was ever asked of the scores.
        return "No player matched these filters."

    if unavailable:
        blocked = ", ".join(item.label for item in unavailable)
        return (
            f"No player could be ranked: {blocked} cannot be produced from the loaded "
            "data. Every candidate needs all of the requested scores, so a profile "
            "weighting one that does not exist matches nobody. Removing it from the "
            "profile will help; narrowing the filters will not."
        )
    return (
        f"{considered} players matched the filters, but none could be given every "
        "requested score - usually too few comparable players in their competition "
        "and position to rank against."
    )


@router.post("/replacement/search", response_model=ReplacementResponse)
def replacement_search(request: ReplacementRequest) -> ReplacementResponse:
    """Find candidates to replace a specific player.

    Combines statistical similarity, role fit and market fit in the proportions
    the spec sets out (section 15). Market fit is only a component when the
    caller supplied a budget; otherwise there is nothing to fit against and its
    weight is redistributed rather than invented.
    """
    view = get_analytics_view()
    target = require_player(view, request.player_id)
    target_fit = view.best_roles.get(request.player_id)
    target_role = target_fit.best.key if target_fit and target_fit.best else None

    filters = request.filters
    similarity_filters = SimilarityFilters(
        min_age=filters.min_age,
        max_age=filters.max_age,
        max_market_value_eur=filters.max_market_value_eur,
        competitions=frozenset(filters.competitions) if filters.competitions else None,
        nationalities=frozenset(filters.nationalities) if filters.nationalities else None,
        contract_expiring_within_months=filters.contract_expiring_within_months,
    )
    similar = view.similar(
        request.player_id,
        filters=similarity_filters,
        limit=request.limit * 4,
        minimum_minutes=filters.min_minutes or 900,
    )

    budget = filters.max_market_value_eur
    candidates: list[ReplacementCandidate] = []

    for result in similar:
        record = view.get(result.candidate.player_key)
        if record is None or not _passes_filters(record, filters):
            continue

        role_score: float | None = None
        if target_role and view.roles is not None:
            metrics = view.player_metrics(record.player_key)
            if metrics is not None:
                role_definition = view.roles.roles.get(target_role)
                if role_definition and role_definition.applies_to(record.position_group):
                    role_score = view.roles.score(metrics, target_role).score

        market_fit: float | None = None
        if budget and record.market_value_eur is not None:
            # Cheaper is a better fit against a fixed budget; at or above it,
            # zero. This is affordability, not value for money.
            market_fit = max(0.0, min(1.0, 1.0 - record.market_value_eur / budget)) * 100.0

        parts = [
            ScoreComponent("similarity", SIMILARITY_WEIGHT * 100, result.similarity),
            ScoreComponent("role_fit", ROLE_WEIGHT * 100, role_score),
            ScoreComponent("market_fit", MARKET_WEIGHT * 100, market_fit),
        ]
        # Role fit or market fit may be absent; the remaining weights are
        # renormalised rather than the missing part counting as zero.
        overall = weighted_score(parts, min_coverage=SIMILARITY_WEIGHT)
        if overall.score is None:
            continue

        candidates.append(
            ReplacementCandidate(
                player=to_summary(record, view),
                overall=overall.score,
                similarity=result.similarity,
                role_fit=role_score,
                market_fit=market_fit,
                comparable_strength=result.comparable_strength,
            )
        )

    candidates.sort(key=lambda c: c.overall, reverse=True)
    return ReplacementResponse(
        target=to_summary(target, view),
        items=candidates[: request.limit],
        meaning=REPLACEMENT_MEANING,
    )


@router.get("/opportunities", response_model=OpportunitiesResponse)
def market_opportunities(
    max_age: int = Query(default=23, ge=14, le=50),
    min_role_score: float = Query(default=80.0, ge=0, le=100),
    min_minutes: int = Query(default=900, ge=0),
    max_market_value_eur: int = Query(default=5_000_000, ge=0),
    contract_within_months: int | None = Query(default=18, ge=0, le=120),
    limit: int = Query(default=25, ge=1, le=100),
) -> OpportunitiesResponse:
    """Players matching a screen over age, role fit, playing time and market.

    Section 16: nobody is labelled undervalued. The response says what the list
    does claim and shows why each player appeared.
    """
    view = get_analytics_view()
    criteria = [
        f"Age at most {max_age}",
        f"Best role score at least {min_role_score:.0f}",
        f"At least {min_minutes} minutes",
        f"Market value at most €{max_market_value_eur / 1_000_000:.1f}m",
    ]
    if contract_within_months is not None:
        criteria.append(f"Contract expiring within {contract_within_months} months")

    found: list[OpportunityOut] = []
    for record in view.players.values():
        if record.age is None or record.age > max_age:
            continue
        if (record.minutes or 0) < min_minutes:
            continue
        if record.market_value_eur is None or record.market_value_eur > max_market_value_eur:
            continue

        fit = view.best_roles.get(record.player_key)
        best = fit.best if fit else None
        if best is None or best.score is None or best.score < min_role_score:
            continue

        reasons = [
            f"{best.label} fit {best.score:.0f}/100",
            f"{record.age} years old",
            f"{record.minutes:,} minutes played",
            f"Valued at €{record.market_value_eur / 1_000_000:.1f}m",
        ]
        if contract_within_months is not None:
            if record.contract_expires is None:
                continue
            months = (record.contract_expires.year - REFERENCE_DATE.year) * 12 + (
                record.contract_expires.month - REFERENCE_DATE.month
            )
            if months > contract_within_months:
                continue
            reasons.append(f"Contract expires {record.contract_expires:%b %Y}")

        found.append(
            OpportunityOut(
                player=to_summary(record, view),
                best_role_score=best.score,
                reasons=reasons,
            )
        )

    found.sort(key=lambda o: o.best_role_score or 0.0, reverse=True)
    return OpportunitiesResponse(
        items=found[:limit],
        total=len(found),
        criteria=criteria,
        disclaimer=OPPORTUNITY_DISCLAIMER,
    )


def _view() -> AnalyticsView:  # pragma: no cover - kept for symmetry with tests
    return get_analytics_view()
