"""Recruitment, replacement and market opportunity endpoints.

All three rank players, and all three must explain why. A shortlist a
recruitment department cannot interrogate is not usable, so every candidate
carries the component percentiles or the reasons that placed it there.

None of the weightings a user supplies leave the server, and none of the
underlying definitions do either (spec section 28).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query

from app.analytics.contracts import expires_within
from app.analytics.intelligence import ScoreDefinition
from app.analytics.percentiles import PercentileScope
from app.analytics.presets import get_presets
from app.analytics.reliability import rank_by_evidence
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
    RolePresetOut,
    ScoreAvailabilityOut,
    ScoreComponentOut,
    ScreenStepOut,
    UnavailableScoreOut,
)
from app.services.analytics_service import (
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
    return filters.contract_expiring_within_months is None or expires_within(
        record.contract_expires, filters.contract_expiring_within_months
    )


@router.get("/recruitment/presets", response_model=list[RolePresetOut])
def list_recruitment_presets() -> list[RolePresetOut]:
    """Named roles as builder weights.

    The builder opens on one profile and asks for eight numbers before it will
    do anything, which is a poor question to put to someone who knows the role
    they want but not how much "defensive activity" it is. These answer it
    from the role definitions the rest of the system already uses, so a preset
    cannot drift away from the role it is named after.
    """
    blocked = _unavailable_scores()
    presets = []
    for preset in get_presets():
        measurable, status, note = _preset_coverage(preset.weights, blocked, preset.label)
        presets.append(
            RolePresetOut(
                key=preset.key,
                label=preset.label,
                description=preset.description,
                position_groups=list(preset.position_groups),
                measurable_pct=measurable,
                coverage_status=status,
                coverage_note=note,
                weights=preset.weights,
                expressible=preset.expressible,
                caveat=preset.caveat,
                unmapped=[metric_label(m) for m in preset.unmapped],
                unavailable_scores=[blocked[k] for k in preset.weights if k in blocked],
            )
        )
    return presets


#: Below this share of measurable weight, a preset no longer describes the role
#: it is named after. Chosen so that losing one secondary emphasis is "limited"
#: and losing a defining one is "minimal"; stated here rather than buried.
LIMITED_COVERAGE = 0.85
MINIMAL_COVERAGE = 0.55


def _preset_coverage(
    weights: dict[str, float],
    blocked: dict[str, UnavailableScoreOut],
    label: str,
) -> tuple[float, str, str | None]:
    """How much of a preset this load can measure, and what to say about it."""
    total = sum(weights.values())
    if total <= 0:
        return 100.0, "full", None
    lost = sum(weight for key, weight in weights.items() if key in blocked)
    measurable = (total - lost) / total

    if not lost:
        return 100.0, "full", None

    names = ", ".join(blocked[k].label for k in weights if k in blocked)
    status = (
        "minimal"
        if measurable < MINIMAL_COVERAGE
        else ("limited" if measurable < LIMITED_COVERAGE else "full")
    )
    note = (
        f"{measurable * 100:.0f}% of this preset's configured weight is measurable "
        f"with the current provider data. {names} cannot be produced for anybody, "
        f"so setting those weights to zero leaves a search that no longer covers "
        f"everything {label} is named for."
    )
    return measurable * 100.0, status, note


@router.get("/recruitment/scores", response_model=list[ScoreAvailabilityOut])
def list_recruitment_scores() -> list[ScoreAvailabilityOut]:
    """The eight emphases, and which of them this load can actually produce.

    The builder used to answer that only after a search: you set a weight, you
    pressed the button, and an empty result came back blaming filters that
    were not the problem. A score no player can be given is a property of the
    data, knowable before anybody clicks.
    """
    view = get_analytics_view()
    if view.intelligence is None:
        raise HTTPException(status_code=503, detail="Analytics unavailable")

    blocked = _unavailable_scores()
    return [
        ScoreAvailabilityOut(
            key=key,
            label=definition.label,
            description=definition.description,
            available=key not in blocked,
            missing=blocked[key].missing if key in blocked else [],
            reason=blocked[key].reason if key in blocked else None,
        )
        for key, definition in view.intelligence.definitions.items()
    ]


def _unavailable_scores() -> dict[str, UnavailableScoreOut]:
    """Scores the loaded data cannot produce for anybody, keyed by score.

    The same sentence the search already returns, reached without running one.
    """
    view = get_analytics_view()
    if view.intelligence is None:
        return {}
    return {
        key: UnavailableScoreOut(
            key=key,
            label=view.intelligence.definitions[key].label,
            missing=list(missing),
            reason=_why_unavailable(view.intelligence.definitions[key], sorted(missing)),
        )
        for key, missing in view.unproducible_scores().items()
    }


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

    # Ordered by evidence, not by the raw composite. A validation audit found
    # a creative-winger brief whose entire top ten came from players with
    # under 320 minutes - the first had 66 - because a per-90 percentile from
    # two appearances is as extreme as the data allows and nothing in the
    # ordering accounted for that. Every one of those players is still here
    # and still scored; they are no longer at the top by default.
    adjustments = rank_by_evidence([c.score for c in ranked], [c.player.minutes for c in ranked])
    for candidate, adjustment in zip(ranked, adjustments, strict=True):
        candidate.ranking_score = adjustment.ranked
        candidate.evidence_weight = adjustment.weight
        candidate.ranking_note = adjustment.explain(
            minutes=candidate.player.minutes, noun="profile score"
        )
    ranked.sort(key=lambda c: c.ranking_score, reverse=True)
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
        is_mock=view.is_mock,
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
        minimum_minutes=filters.min_minutes or 0,
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

        # A validation audit measured what renormalising does to the ORDER.
        # Because similarity is almost always the highest of the three parts,
        # dropping role fit RAISES the renormalised result: the average
        # overall for candidates missing it was 81.0 against 76.8 for those
        # that had it. Missing evidence was improving a candidate's rank.
        #
        # Zero-filling is not the answer - it would invent a measurement - so
        # the comparable score is withheld instead. The candidate keeps every
        # number that was actually computed, stays in the response, and is
        # listed after the candidates whose score means the same thing.
        missing_components = [
            label
            for label, value in (("Role fit", role_score), ("Affordability", market_fit))
            if value is None and label in _required_components(target_role, budget)
        ]
        candidates.append(
            ReplacementCandidate(
                player=to_summary(record, view),
                overall=None if missing_components else overall.score,
                similarity=result.similarity,
                role_fit=role_score,
                market_fit=market_fit,
                comparable_strength=result.comparable_strength,
                missing_components=missing_components,
                candidate_minutes=record.minutes,
            )
        )

    # Two groups, never interleaved: candidates with a complete score, then
    # candidates whose score could not be completed. Inside each group the
    # order is evidence-adjusted, so a 28-minute profile no longer leads a
    # list of replacements for a player with a full season behind him.
    complete = [c for c in candidates if c.overall is not None]
    limited = [c for c in candidates if c.overall is None]
    _order_by_evidence(complete, value=lambda c: c.overall or 0.0, noun="replacement score")
    _order_by_evidence(limited, value=lambda c: c.similarity, noun="similarity")

    ordered = complete + limited
    return ReplacementResponse(
        target=to_summary(target, view),
        items=ordered[: request.limit],
        meaning=REPLACEMENT_MEANING,
        complete_count=len(complete),
    )


def _required_components(target_role: str | None, budget: int | None) -> set[str]:
    """Which parts must be present for a replacement score to be comparable.

    Role fit is required only when the target actually has a role to be
    replaced in; affordability only when a budget was given. Asking for a
    component nobody could supply would withhold every score and tell the
    reader nothing.
    """
    required: set[str] = set()
    if target_role is not None:
        required.add("Role fit")
    if budget:
        required.add("Affordability")
    return required


def _order_by_evidence(
    candidates: list[ReplacementCandidate],
    *,
    value: Callable[[ReplacementCandidate], float],
    noun: str,
) -> None:
    """Sort in place by the evidence-adjusted value, and say so on each row."""
    adjustments = rank_by_evidence(
        [value(c) for c in candidates], [c.candidate_minutes for c in candidates]
    )
    for candidate, adjustment in zip(candidates, adjustments, strict=True):
        candidate.ranking_value = adjustment.ranked
        candidate.evidence_weight = adjustment.weight
        candidate.ranking_note = adjustment.explain(minutes=candidate.candidate_minutes, noun=noun)
    candidates.sort(key=lambda c: c.ranking_value, reverse=True)


@router.get("/opportunities", response_model=OpportunitiesResponse)
def market_opportunities(
    max_age: int = Query(default=23, ge=14, le=50),
    min_role_score: float = Query(default=80.0, ge=0, le=100),
    # Not 900. A default nobody asked for that excludes anyone with fewer
    # than ten full matches is a filter disguised as a sensible baseline;
    # four matches into a season it screens out the entire population. The
    # funnel below reports the floor that was actually applied.
    min_minutes: int = Query(default=0, ge=0),
    max_market_value_eur: int = Query(default=5_000_000, ge=0),
    contract_within_months: int | None = Query(default=18, ge=0, le=120),
    limit: int = Query(default=25, ge=1, le=100),
) -> OpportunitiesResponse:
    """Players matching a screen over age, role fit, playing time and market.

    Section 16: nobody is labelled undervalued. The response says what the list
    does claim and shows why each player appeared.
    """
    view = get_analytics_view()
    # Each criterion carries its own test. Holding the wording in one list and
    # the tests in another let them drift apart, and a funnel that labels the
    # minutes filter "Raw role fit at least 80" is worse than no funnel: it
    # is a confident account of the wrong thing.
    steps: list[tuple[str, Callable[[PlayerRecord], bool]]] = [
        (
            f"Age at most {max_age}",
            lambda r: r.age is not None and r.age <= max_age,
        ),
        (
            f"Raw role fit at least {min_role_score:.0f}",
            lambda r: _best_role_score(view, r) >= min_role_score,
        ),
        (
            f"At least {min_minutes} minutes",
            lambda r: (r.minutes or 0) >= min_minutes,
        ),
        (
            f"Market value at most €{max_market_value_eur / 1_000_000:.1f}m",
            lambda r: r.market_value_eur is not None and r.market_value_eur <= max_market_value_eur,
        ),
    ]
    if contract_within_months is not None:
        steps.append(
            (
                f"Contract expiring within {contract_within_months} months",
                lambda r: expires_within(r.contract_expires, contract_within_months),
            )
        )
    criteria = [label for label, _ in steps]

    surviving = list(view.players.values())
    funnel: list[ScreenStepOut] = []
    for label, passes in steps:
        before = len(surviving)
        surviving = [r for r in surviving if passes(r)]
        funnel.append(
            ScreenStepOut(
                criterion=label, remaining=len(surviving), removed=before - len(surviving)
            )
        )

    found: list[OpportunityOut] = []
    for record in surviving:
        fit = view.best_roles.get(record.player_key)
        best = fit.best if fit else None
        # The screen above already required all three; restated here because a
        # filter in a lambda is not narrowing a type checker can follow, and
        # asserting it would turn a data condition into a crash.
        if best is None or best.score is None or record.market_value_eur is None:
            continue  # pragma: no cover - the screen guarantees these

        reasons = [
            f"{best.label} fit {best.score:.0f}/100",
            f"{record.age} years old",
            f"{record.minutes:,} minutes played",
            f"Valued at €{record.market_value_eur / 1_000_000:.1f}m",
        ]
        if contract_within_months is not None and record.contract_expires is not None:
            reasons.append(f"Contract expires {record.contract_expires:%b %Y}")

        found.append(
            OpportunityOut(
                player=to_summary(record, view),
                best_role_score=best.score,
                reasons=reasons,
            )
        )

    # Ordered by evidence, not by the raw fit.
    #
    # This is a discovery surface and it was putting a Raw Fit of 98 from 24
    # minutes above a 93 from a full season. Both percentiles are honest; they
    # are not equally strong evidence that a player is worth pursuing, and an
    # ordering that cannot tell them apart sends a scout to the wrong name
    # first.
    #
    # The same utility the replacement finder and the recruitment builder use,
    # deliberately rather than a second formula: one way of reading thin
    # evidence, applied in every place the product ranks anybody. Nobody is
    # removed, no minutes floor appears, and `best_role_score` is untouched -
    # it is still what the page shows as Raw Fit, and still what the Role Fit
    # Percentile is built from.
    #
    # The prior is the average role fit of every player who HAS one, not of
    # the survivors. The screen runs before the ranking, so the survivors are
    # an elite by construction: shrinking toward their average told every thin
    # candidate they were probably excellent. Measured on the live list, a
    # 57-minute fit of 81 would have been read as 87.8 and ranked second,
    # above a 973-minute 84 read as 83.8 and ranked twelfth. Nobody intended
    # an ordering that rewards having played less.
    adjustments = rank_by_evidence(
        [o.best_role_score or 0.0 for o in found],
        [o.player.minutes for o in found],
        mean=_ordinary_role_fit(view),
    )
    for opportunity, adjustment in zip(found, adjustments, strict=True):
        opportunity.ranking_score = adjustment.ranked
        opportunity.evidence_weight = adjustment.weight
        opportunity.ranking_note = adjustment.explain(
            minutes=opportunity.player.minutes,
            noun="role fit",
            # Not "for this search": the screen runs first, so the average of
            # what is on screen is an elite's. The number in the sentence is
            # the one the shrinkage actually used.
            centre="across every player with a role fit",
        )

    found.sort(key=lambda o: o.ranking_score, reverse=True)
    return OpportunitiesResponse(
        items=found[:limit],
        total=len(found),
        criteria=criteria,
        disclaimer=OPPORTUNITY_DISCLAIMER,
        funnel=funnel,
        explanation=_explain_screen(funnel, len(found)),
        is_mock=view.is_mock,
    )


def _ordinary_role_fit(view: AnalyticsView) -> float:
    """What an ordinary player's best role fit looks like, across everybody.

    The centre a short sample is read toward on the Opportunities screen. It
    is deliberately measured over every player who has a role fit at all,
    rather than over the handful who cleared the screen: the screen selects
    for a high fit, so its survivors' average describes an elite and shrinking
    toward it is a compliment rather than a correction.

    Zero players with a fit returns 0.0, which cannot happen alongside a
    non-empty result - the screen requires a fit - and is the right answer if
    it somehow did.
    """
    scores = [
        fit.best.score
        for fit in view.best_roles.values()
        if fit.best is not None and fit.best.score is not None
    ]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _best_role_score(view: AnalyticsView, record: PlayerRecord) -> float:
    """The player's best role score, or below any threshold when there is none.

    A player with no role score has not scored badly - most often there were
    too few comparable players in their competition to rank them at all. The
    screen still has to exclude them, and the funnel is where that shows.
    """
    fit = view.best_roles.get(record.player_key)
    if fit is None or fit.best is None or fit.best.score is None:
        return -1.0
    return fit.best.score


def _explain_screen(funnel: list[ScreenStepOut], found: int) -> str | None:
    """Name the criterion that did the most narrowing, when the result is thin.

    Five criteria and one survivor is either a strict screen or a broken one,
    and the list cannot tell them apart. The binding constraint usually can.
    """
    if found > 10 or not funnel:
        return None

    strictest = max(funnel, key=lambda step: step.removed)
    if strictest.removed == 0:
        return None
    started = funnel[0].remaining + funnel[0].removed
    return (
        f"{found} of {started:,} players cleared every criterion. "
        f'Most were removed by "{strictest.criterion}" ({strictest.removed:,} players); '
        f"{funnel[-1].remaining:,} survived the full screen."
    )


def _view() -> AnalyticsView:  # pragma: no cover - kept for symmetry with tests
    return get_analytics_view()
