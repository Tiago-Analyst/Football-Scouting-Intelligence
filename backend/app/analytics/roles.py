"""Player role engine.

Scores how closely a player's statistical profile resembles a style of play, and
reports the best fit alongside the alternatives.

What a role score is **not** (spec section 31, rules 20 and 21): it is not
player quality, not a probability, and not a scouting grade. A player can score
90 for a role and be a poor signing — the score knows nothing about tactical
system, physical data, injury record, or what a scout sees. `ROLE_SCORE_MEANING`
carries that wording so it travels with the number rather than living only in
documentation.

Definitions live in `config/player_roles.yaml`. A role's components can be
derived metrics or whole intelligence scores — the Ball-Winning Midfielder
weights Ball Security at 10%, because keeping the ball after winning it is part
of the role. The two namespaces are kept separate in config so a name is never
ambiguous.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml

from app.analytics.intelligence import (
    IntelligenceScoreEngine,
    ScoreConfigError,
    widest_context,
)
from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric
from app.analytics.percentiles import (
    ComparisonContext,
    PercentileScope,
    PlayerMetrics,
    percentile_of,
)
from app.analytics.scoring import ScoreComponent, ScoreResult, weighted_score
from app.core import paths
from app.schemas.canonical import PositionGroup

REPO_ROOT = paths.REPO_ROOT
DEFAULT_ROLES_PATH = REPO_ROOT / "config" / "player_roles.yaml"

#: Below this, a role has too few players evaluated for a standing within it to
#: mean anything. Matches MIN_POPULATION in the percentile engine: the argument
#: is the same one - a rank against four players is noise wearing a number.
MIN_ROLE_POPULATION = 10

ROLE_SCORE_MEANING = (
    "Raw Role Fit is the statistical resemblance between a player's profile and "
    "a role definition, on a 0-100 scale, built from the components shown. Role "
    "Fit Percentile is where that score stands among every player evaluated for "
    "the same role, and it is the comparable one: raw scores from differently "
    "weighted roles do not share a scale. Neither is player quality, a "
    "probability, or a scouting grade."
)


class RoleCoverage(StrEnum):
    """How much of a role's own definition was available to score it.

    A role is scored from the components the provider actually supplies, with
    the remaining weights renormalised - otherwise a missing 30% component
    would drag every score down by a third and read as poor performance rather
    than absent data. That renormalisation is right and it is also exactly what
    makes this enum necessary: once the weights are rescaled, a score built
    from 60% of a definition looks identical to one built from all of it.

    So the original coverage is reported separately and banded, and the band
    travels with the score everywhere it is shown.
    """

    #: Scored from essentially the whole definition.
    FULL = "full"
    #: A component or two missing. The role still measures what it claims to.
    REDUCED = "reduced"
    #: Enough of the definition is missing that the label overstates what was
    #: measured. Shown, with its caveat, and never presented as equivalent.
    LIMITED = "limited"


#: At or above this, a role is scored from all but a rounding error.
FULL_COVERAGE = 0.95

#: Below this, the role is LIMITED. Chosen so the two roles whose defining
#: component the provider does not supply - ball-playing centre-back at 60%,
#: deep-lying playmaker at 70% - land there, while roles missing a single
#: secondary component do not. It is a judgement, not a discovery, and it is
#: written down here rather than implied by a comparison somewhere.
LIMITED_COVERAGE = 0.75


def classify_role_coverage(coverage: float) -> RoleCoverage:
    """Band a role's metric coverage."""
    if coverage >= FULL_COVERAGE:
        return RoleCoverage.FULL
    if coverage >= LIMITED_COVERAGE:
        return RoleCoverage.REDUCED
    return RoleCoverage.LIMITED


ROLE_COVERAGE_LABELS: dict[RoleCoverage, str] = {
    RoleCoverage.FULL: "Full coverage",
    RoleCoverage.REDUCED: "Reduced coverage",
    RoleCoverage.LIMITED: "Limited coverage",
}


class RoleConfigError(Exception):
    """The role configuration is malformed or names something unknown."""


@dataclass(frozen=True)
class RoleDefinition:
    """One role, as configured."""

    key: str
    label: str
    description: str
    position_groups: tuple[PositionGroup, ...]
    metric_weights: dict[DerivedMetric, float]
    score_weights: dict[str, float]
    #: RETIRED AS A VALIDITY GATE. Kept for migration, diagnostics and the
    #: record, never consulted when deciding whether a role may be scored.
    #:
    #: Measured across all fifteen roles, thirteen had this set to exactly one
    #: point below the maximum coverage the provider could reach - so it
    #: encoded what the data happened to supply rather than what a role needs,
    #: and it did so one metric away from silence. It also ran BEFORE core
    #: validity, which made the football gate secondary to an availability
    #: readout: twelve full-backs with both core dimensions satisfied were
    #: refused a score at 70% against this role's 79%.
    #:
    #: `SECONDARY_COVERAGE_FLOOR` is the only coverage gate now.
    legacy_min_coverage: float = 1.0
    caveat: str | None = None
    #: The football concepts without which this role is not this role, each
    #: satisfiable by ANY of the metrics listed against it. Dimensions rather
    #: than mandatory metrics, because a concept usually has more than one way
    #: to be evidenced and a provider supplying a different one should not
    #: silence the role.
    core_dimensions: dict[str, tuple[DerivedMetric, ...]] = field(default_factory=dict)

    @property
    def primary_position(self) -> PositionGroup:
        """The group the specification assigns this role."""
        return self.position_groups[0]

    def applies_to(self, position_group: PositionGroup | None) -> bool:
        return position_group is not None and position_group in self.position_groups

    @property
    def inverted_metrics(self) -> tuple[DerivedMetric, ...]:
        return tuple(m for m in self.metric_weights if m in LOWER_IS_BETTER)


class RoleValidity(StrEnum):
    """Whether a role's football meaning survived the data.

    Separate from coverage on purpose, because they answer different
    questions. Coverage asks how much of the configured definition could be
    measured. Validity asks whether the concepts that make the role that role
    are measurable at all - and a percentage cannot tell the two apart. A
    Ball-Playing Centre-Back scored without any measure of progression sits at
    60% coverage and is not a ball-playing centre-back; a Defensive Full-Back
    missing only how often he is dribbled past can still be read as a
    defensive full-back, because duels evidence the same thing.
    """

    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CoreDimensionStatus:
    """One defining concept of a role, and whether anything evidenced it."""

    name: str
    satisfied: bool
    available: tuple[str, ...]
    missing: tuple[str, ...]


#: Below this share of the configured weight, whatever is left is too partial
#: to call a role fit at all.
#:
#: PROVISIONAL. It is a technical guardrail, not a methodological finding, and
#: it has never been validated against football judgement - on the current data
#: it binds on no role, so nothing has tested it but intent. It is deliberately
#: one number for every role rather than fifteen tuned ones, because fifteen
#: would invite the same mistake `min_coverage` already made: thresholds that
#: encode what the provider happens to supply rather than what a role needs.
#:
#: Changing it is a football decision, not a technical one.
SECONDARY_COVERAGE_FLOOR = 0.50


@dataclass(frozen=True)
class RoleScore:
    """A computed role fit with everything needed to explain it."""

    key: str
    label: str
    score: float | None
    coverage: float
    context: ComparisonContext
    components: list[ScoreComponent]
    missing: list[str]
    caveat: str | None = None
    #: Where this raw score sits among every player evaluated for this same
    #: role. `None` when no distribution was available - see `normalise_fits`.
    role_fit_percentile: float | None = None
    #: How many players that standing was measured against.
    role_population: int = 0
    #: Whether the role's defining concepts could be measured for this player.
    validity: RoleValidity = RoleValidity.FULL
    #: Each defining concept and what evidenced it, for a page to explain with.
    core_dimensions: tuple[CoreDimensionStatus, ...] = ()
    #: Why no standard percentile is published, when none is.
    role_fit_percentile_reason: str | None = None
    #: The same, as a stable code and the values its sentence needs.
    #:
    #: Decided here rather than at the API boundary, because this is where the
    #: three cases are actually told apart. Re-deriving them from the English
    #: sentence one layer up would be the pattern-matching these codes exist
    #: to remove.
    role_fit_percentile_reason_code: str | None = None
    #: Unmet dimensions as configured identifiers, for the code above.
    role_fit_percentile_unmet: tuple[str, ...] = ()

    @property
    def is_full(self) -> bool:
        return self.validity is RoleValidity.FULL

    @property
    def unmet_dimensions(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.core_dimensions if not d.satisfied)

    @property
    def is_available(self) -> bool:
        return self.score is not None

    @property
    def availability_note(self) -> str | None:
        """What was missing, generated from what was actually missing.

        WHY THIS IS NOT WRITTEN BY HAND

        It was, in `caveat`, and the hand-written text went stale exactly as
        one would expect. The Ball-Winning Midfielder caveat said it was
        computed without the ball security score; ball security has been fully
        available for some time. The Direct Winger caveat said it was computed
        without inverse dispossessions; that role is at 100% coverage with
        nothing missing at all.

        Both were true when written. Neither had any way of noticing the
        provider had started supplying the field, so the site went on
        apologising for data it had.

        A quantitative availability claim is derivable, so it is derived.
        `caveat` keeps only what cannot be: the qualitative methodological
        limitations - that tackle counts are attempts rather than successes,
        that goalkeeping figures are team-dependent - which no availability
        report can know.
        """
        if not self.missing:
            return None
        names = ", ".join(sorted(self.missing))
        return (
            f"Computed from {self.coverage:.0%} of this role's configured weight. "
            f"Not available from the performance provider: {names}. The remaining "
            f"components are reweighted to sum to 100%; nothing missing is counted "
            f"as zero."
        )

    @property
    def explanation(self) -> str | None:
        """The availability note and the methodological caveat, in that order.

        One string for the interface, so the two cannot be shown apart or get
        out of order.
        """
        parts = [self.availability_note, self.caveat]
        joined = " ".join(part.strip() for part in parts if part)
        return joined or None

    @property
    def coverage_band(self) -> RoleCoverage:
        """How much of this role's definition was behind the score."""
        return classify_role_coverage(self.coverage)

    @property
    def coverage_label(self) -> str:
        return ROLE_COVERAGE_LABELS[self.coverage_band]

    @property
    def is_limited(self) -> bool:
        """Whether the label overstates what was actually measured.

        Not the same question as `is_available`. A limited role has a real
        score, computed from real data; what it does not have is the component
        that gives the role its name.
        """
        return self.coverage_band is RoleCoverage.LIMITED

    @property
    def standing(self) -> float:
        """What to rank this role by when choosing a player's best.

        The percentile where there is one, the raw score otherwise. Comparing
        raw scores across roles is not quite fair - see `normalise_fits` - but
        it is better than refusing to name a best role at all.
        """
        if self.role_fit_percentile is not None:
            return self.role_fit_percentile
        return self.score or 0.0

    def contributions(self) -> list[tuple[str, float]]:
        result = ScoreResult(
            score=self.score,
            coverage=self.coverage,
            components=self.components,
            missing=self.missing,
        )
        return sorted(result.contributions(), key=lambda item: item[1], reverse=True)


@dataclass(frozen=True)
class RoleFit:
    """A player's fit across every role compatible with their position."""

    best: RoleScore | None
    alternatives: list[RoleScore]
    #: Roles whose defining concepts this data cannot fully measure, strongest
    #: raw fit first. Reported beside the best role, never as it: the number is
    #: real and the comparison is not.
    partial_evidence: list[RoleScore] = field(default_factory=list)

    @property
    def all_scores(self) -> list[RoleScore]:
        return ([self.best] if self.best else []) + self.alternatives + self.partial_evidence

    @property
    def meaning(self) -> str:
        """What the number does and does not claim. Returned with the fit so it
        cannot be separated from it."""
        return ROLE_SCORE_MEANING


def normalise_fits(fits: dict[str, RoleFit]) -> dict[str, RoleFit]:
    """Place every raw role score within its own role's distribution.

    WHY THIS EXISTS
    ---------------

    Raw role scores are weighted averages of percentiles, and they do not share
    a scale. How much they diverge depends on how the weight is spread. A role
    with one dominant component inherits that component's spread almost intact,
    so its scores run high and low freely. A role with six evenly weighted
    components averages six percentiles together, and averaging pulls results
    towards the middle - so its very best players score lower than the very
    best of the concentrated role, while being no less suited to it.

    Measured on the loaded data: Shot Stopper, with a large top weight, reaches
    much further up the scale than Box-to-Box, whose weights are spread evenly.
    Comparing 72 against 78 across those two roles is comparing distributions,
    not players.

    So a second number is computed here: where a player's raw score sits among
    everybody evaluated for that same role. That comparison is within one
    distribution and is therefore fair, and it is what `best` is chosen by.

    The raw score is kept and shown. It is the explainable one - it decomposes
    into the components that produced it - and replacing it would trade an
    interpretable number for a relative one. Neither is player quality.

    Roles with too few players to rank against keep a `None` percentile and
    fall back to their raw score, which is stated rather than hidden.
    """
    # ONLY FULL SCORES BUILD THE DISTRIBUTION.
    #
    # A percentile says where a score stands among others measured the same
    # way. A Ball-Playing Centre-Back scored without any measure of
    # progression was not measured the same way as one scored with it, and
    # ranking the two together is exactly the comparison the missing metric
    # forbids. Partial scores are therefore neither placed nor used to place
    # anyone else; their raw fit is reported and the percentile is withheld
    # with the reason attached.
    by_role: dict[str, list[float]] = defaultdict(list)
    for fit in fits.values():
        for score in fit.all_scores:
            if score.score is not None and score.is_full:
                by_role[score.key].append(score.score)
    for values in by_role.values():
        values.sort()

    def placed(score: RoleScore) -> RoleScore:
        values = by_role.get(score.key, [])
        if not score.is_full:
            unmet = ", ".join(score.unmet_dimensions)
            reason = (
                f"This role could not be measured for {unmet}, so its score is not "
                f"comparable with players scored from the full definition."
                if unmet
                else "Too little of this role's definition could be measured."
            )
            return replace(
                score,
                role_fit_percentile=None,
                role_population=len(values),
                role_fit_percentile_reason=reason,
                role_fit_percentile_reason_code=(
                    "role_partial_definition" if unmet else "role_definition_unmeasurable"
                ),
                role_fit_percentile_unmet=tuple(score.unmet_dimensions),
            )
        if score.score is None or len(values) < MIN_ROLE_POPULATION:
            return replace(
                score,
                role_fit_percentile=None,
                role_population=len(values),
                role_fit_percentile_reason=(
                    "Too few players were evaluated for this role to place a score among them."
                ),
                role_fit_percentile_reason_code="role_population_too_small",
            )
        return replace(
            score,
            role_fit_percentile=percentile_of(score.score, values),
            role_population=len(values),
        )

    normalised: dict[str, RoleFit] = {}
    for key, fit in fits.items():
        scores = [placed(s) for s in fit.all_scores]
        full = sorted((s for s in scores if s.is_full), key=lambda s: s.standing, reverse=True)
        partial = sorted(
            (s for s in scores if s.validity is RoleValidity.PARTIAL),
            key=lambda s: s.score or 0.0,
            reverse=True,
        )
        # The best role is the best FULLY SUPPORTED role, and partial evidence
        # is surfaced beside it rather than competing with it. Letting a
        # partial score win would present an incomparable number as the
        # headline; dropping it would hide a real finding about a player whose
        # strongest statistical case happens to sit in a role this data cannot
        # fully measure.
        normalised[key] = RoleFit(
            best=full[0] if full else None,
            alternatives=full[1:],
            partial_evidence=partial,
        )
    return normalised


def load_roles(
    path: Path = DEFAULT_ROLES_PATH,
    *,
    known_scores: set[str] | None = None,
) -> dict[str, RoleDefinition]:
    """Read and validate role definitions.

    Strict on purpose: an unknown metric, an unknown intelligence score or an
    unknown position group raises rather than being skipped. A silently dropped
    component would change the role's meaning while leaving no trace.
    """
    if not path.exists():
        raise RoleConfigError(f"Role config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles = raw.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise RoleConfigError(f"No roles defined in {path}")

    known_metrics = {m.value: m for m in DerivedMetric}
    known_groups = {g.value: g for g in PositionGroup}
    definitions: dict[str, RoleDefinition] = {}

    for key, body in roles.items():
        if not isinstance(body, dict):
            raise RoleConfigError(f"Role '{key}' must be a mapping")

        groups_raw = body.get("position_groups")
        if not isinstance(groups_raw, list) or not groups_raw:
            raise RoleConfigError(f"Role '{key}' must list at least one position group")
        groups: list[PositionGroup] = []
        for name in groups_raw:
            group = known_groups.get(str(name))
            if group is None:
                raise RoleConfigError(f"Role '{key}' names unknown position group '{name}'")
            groups.append(group)

        components = body.get("components")
        if not isinstance(components, dict) or not components:
            raise RoleConfigError(f"Role '{key}' defines no components")

        metric_weights: dict[DerivedMetric, float] = {}
        for name, weight in (components.get("metrics") or {}).items():
            metric = known_metrics.get(str(name))
            if metric is None:
                raise RoleConfigError(f"Role '{key}' references unknown metric '{name}'")
            if not isinstance(weight, int | float) or weight <= 0:
                raise RoleConfigError(f"Role '{key}' metric '{name}' needs a positive weight")
            metric_weights[metric] = float(weight)

        score_weights: dict[str, float] = {}
        for name, weight in (components.get("scores") or {}).items():
            if known_scores is not None and str(name) not in known_scores:
                raise RoleConfigError(
                    f"Role '{key}' references unknown intelligence score '{name}'"
                )
            if not isinstance(weight, int | float) or weight <= 0:
                raise RoleConfigError(f"Role '{key}' score '{name}' needs a positive weight")
            score_weights[str(name)] = float(weight)

        if not metric_weights and not score_weights:
            raise RoleConfigError(f"Role '{key}' defines no components")

        min_coverage = float(body.get("min_coverage", 1.0))
        if not 0.0 < min_coverage <= 1.0:
            raise RoleConfigError(f"Role '{key}' min_coverage must be within (0, 1]")

        definitions[key] = RoleDefinition(
            key=key,
            label=str(body.get("label", key)),
            description=str(body.get("description", "")).strip(),
            position_groups=tuple(groups),
            metric_weights=metric_weights,
            score_weights=score_weights,
            legacy_min_coverage=min_coverage,
            core_dimensions=_parse_core_dimensions(key, body.get("core_dimensions"), known_metrics),
            caveat=(str(body["caveat"]).strip() if body.get("caveat") else None),
        )

    return definitions


def _validity(
    score: float | None,
    coverage: float,
    dimensions: tuple[CoreDimensionStatus, ...],
) -> RoleValidity:
    """Core validity first, coverage second. They answer different questions.

    No score, or too little of the definition measured, and there is nothing
    to call a role fit. Otherwise the role is itself only if every defining
    concept was evidenced; short of that it is partial, and the evidence that
    does exist is still real and still reported.

    A role with no configured dimensions is treated as full, because the
    absence of a declaration is not a finding about the football.
    """
    if score is None or coverage < SECONDARY_COVERAGE_FLOOR:
        return RoleValidity.UNAVAILABLE
    if any(not d.satisfied for d in dimensions):
        return RoleValidity.PARTIAL
    return RoleValidity.FULL


def _parse_core_dimensions(
    key: str,
    body: object,
    known: dict[str, DerivedMetric],
) -> dict[str, tuple[DerivedMetric, ...]]:
    """Read a role's defining concepts, or refuse the configuration.

    As strict as the weights. A dimension naming a metric the role does not
    score from would be a requirement nothing could satisfy, and a silent skip
    would turn a defining concept into an optional one.
    """
    if body is None:
        return {}
    if not isinstance(body, dict) or not body:
        raise RoleConfigError(f"Role '{key}' core_dimensions must be a non-empty mapping")
    parsed: dict[str, tuple[DerivedMetric, ...]] = {}
    for name, metrics in body.items():
        if not isinstance(metrics, list) or not metrics:
            raise RoleConfigError(f"Role '{key}' dimension '{name}' needs a list of metrics")
        resolved = []
        for metric_name in metrics:
            metric = known.get(metric_name)
            if metric is None:
                raise RoleConfigError(
                    f"Role '{key}' dimension '{name}' references unknown metric '{metric_name}'"
                )
            resolved.append(metric)
        parsed[str(name)] = tuple(resolved)
    return parsed


@lru_cache(maxsize=1)
def get_roles() -> dict[str, RoleDefinition]:
    """Cached role definitions, validated against the intelligence scores."""
    from app.analytics.intelligence import get_definitions

    return load_roles(known_scores=set(get_definitions()))


class RoleEngine:
    """Scores players against role definitions."""

    def __init__(
        self,
        intelligence: IntelligenceScoreEngine,
        roles: dict[str, RoleDefinition] | None = None,
    ) -> None:
        self.intelligence = intelligence
        self.percentiles = intelligence.percentiles
        self.roles = roles if roles is not None else get_roles()

    def compatible_roles(self, position_group: PositionGroup | None) -> list[RoleDefinition]:
        """Roles a player of this position may be scored against."""
        return [role for role in self.roles.values() if role.applies_to(position_group)]

    def score(
        self,
        player: PlayerMetrics,
        key: str,
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> RoleScore:
        """Score one player against one role."""
        role = self.roles.get(key)
        if role is None:
            raise RoleConfigError(f"Unknown role: {key}")

        components: list[ScoreComponent] = []
        context: ComparisonContext | None = None

        if role.metric_weights:
            metrics = list(role.metric_weights)
            ranked = self.percentiles.rank_all(
                player, metrics, scope=scope, competition_ids=competition_ids
            )
            context = widest_context(ranked.values()) or ranked[metrics[0]].context
            components.extend(
                ScoreComponent(
                    metric=metric.value,
                    weight=role.metric_weights[metric],
                    # Oriented: inverse metrics are already flipped.
                    value=ranked[metric].oriented,
                )
                for metric in metrics
            )

        for score_key, weight in role.score_weights.items():
            # An intelligence score is already a 0-100 composite of percentiles,
            # so it sits on the same scale as the metric components.
            try:
                inner = self.intelligence.score(
                    player, score_key, scope=scope, competition_ids=competition_ids
                )
            except ScoreConfigError as exc:
                raise RoleConfigError(str(exc)) from exc
            # An inner score may itself have leant on a wider population than
            # this role's own metrics did.
            context = max(
                [c for c in (context, inner.context) if c is not None],
                key=lambda c: (len(c.competition_ids), c.population_size),
            )
            components.append(
                ScoreComponent(metric=f"score:{score_key}", weight=weight, value=inner.score)
            )

        if context is None:  # pragma: no cover - config validation prevents this
            raise RoleConfigError(f"Role '{key}' produced no components")

        # CORE VALIDITY IS THE GATE, NOT COVERAGE.
        #
        # The role's own historical floor is deliberately not consulted here.
        # It encoded provider availability rather than football sufficiency,
        # and because it ran first it could refuse a role whose defining
        # concepts were all measured. What remains is a single provisional
        # floor, shared by every role, guarding against data so incomplete
        # that nothing meaningful could be built from it.
        result = weighted_score(components, min_coverage=SECONDARY_COVERAGE_FLOOR)

        # Which defining concepts anything evidenced. A dimension is satisfied
        # by ANY of its metrics, so a full-back missing how often he is
        # dribbled past still has defensive resistance through duels - and a
        # centre-back with no measure of progression does not have progression
        # however high his passing coverage is.
        available = {c.metric for c in result.components if c.is_available}
        dimensions = tuple(
            CoreDimensionStatus(
                name=name,
                satisfied=any(m.value in available for m in metrics),
                available=tuple(m.value for m in metrics if m.value in available),
                missing=tuple(m.value for m in metrics if m.value not in available),
            )
            for name, metrics in role.core_dimensions.items()
        )
        validity = _validity(result.score, result.coverage, dimensions)

        return RoleScore(
            key=role.key,
            label=role.label,
            score=result.score,
            coverage=result.coverage,
            context=context,
            components=result.components,
            missing=result.missing,
            caveat=role.caveat,
            validity=validity,
            core_dimensions=dimensions,
        )

    def fit(
        self,
        player: PlayerMetrics,
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> RoleFit:
        """Score a player against every compatible role, best first.

        Roles that could not be computed are excluded rather than ranked as
        zero: an absent score means unknown fit, and treating it as no fit would
        push a player away from a role they might well suit.
        """
        scored = [
            self.score(player, role.key, scope=scope, competition_ids=competition_ids)
            for role in self.compatible_roles(player.position_group)
        ]
        available = sorted(
            (s for s in scored if s.score is not None),
            key=lambda s: s.score or 0.0,
            reverse=True,
        )
        if not available:
            return RoleFit(best=None, alternatives=[])
        return RoleFit(best=available[0], alternatives=available[1:])
