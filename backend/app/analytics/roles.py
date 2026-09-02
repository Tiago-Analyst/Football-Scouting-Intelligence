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
from dataclasses import dataclass, replace
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
    min_coverage: float = 1.0
    caveat: str | None = None

    @property
    def primary_position(self) -> PositionGroup:
        """The group the specification assigns this role."""
        return self.position_groups[0]

    def applies_to(self, position_group: PositionGroup | None) -> bool:
        return position_group is not None and position_group in self.position_groups

    @property
    def inverted_metrics(self) -> tuple[DerivedMetric, ...]:
        return tuple(m for m in self.metric_weights if m in LOWER_IS_BETTER)


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

    @property
    def is_available(self) -> bool:
        return self.score is not None

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

    @property
    def all_scores(self) -> list[RoleScore]:
        return ([self.best] if self.best else []) + self.alternatives

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
    by_role: dict[str, list[float]] = defaultdict(list)
    for fit in fits.values():
        for score in fit.all_scores:
            if score.score is not None:
                by_role[score.key].append(score.score)
    for values in by_role.values():
        values.sort()

    def placed(score: RoleScore) -> RoleScore:
        values = by_role.get(score.key, [])
        if score.score is None or len(values) < MIN_ROLE_POPULATION:
            return replace(score, role_fit_percentile=None, role_population=len(values))
        return replace(
            score,
            role_fit_percentile=percentile_of(score.score, values),
            role_population=len(values),
        )

    normalised: dict[str, RoleFit] = {}
    for key, fit in fits.items():
        scores = sorted(
            (placed(s) for s in fit.all_scores),
            key=lambda s: s.standing,
            reverse=True,
        )
        normalised[key] = RoleFit(
            best=scores[0] if scores else None,
            alternatives=scores[1:],
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
            min_coverage=min_coverage,
            caveat=(str(body["caveat"]).strip() if body.get("caveat") else None),
        )

    return definitions


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

        result = weighted_score(components, min_coverage=role.min_coverage)
        return RoleScore(
            key=role.key,
            label=role.label,
            score=result.score,
            coverage=result.coverage,
            context=context,
            components=result.components,
            missing=result.missing,
            caveat=role.caveat,
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
