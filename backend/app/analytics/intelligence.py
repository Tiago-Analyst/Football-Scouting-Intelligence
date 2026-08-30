"""Intelligence score engine.

Composite 0-100 scores describing a facet of play: ball progression, ball
security, chance creation, defensive activity, duel dominance, 1v1 threat, goal
threat, finishing.

Definitions live in `config/intelligence_scores.yaml`, not here. The engine
loads them, resolves each component to a contextual percentile, and combines
them — so tuning a weight is a configuration review rather than a code change
(spec section 31, rule 5).

Two properties the engine guarantees:

**Components are percentiles before they are weighted** (spec section 9).
Weighting raw metrics would let progressive passes per 90 (roughly 0-12) be
swamped by pass completion (0-100) for no reason other than their units.

**Every score can be decomposed.** The component percentiles and their
contributions are returned with the score, because a recruitment ranking nobody
can interrogate is not usable by a recruitment department.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric
from app.analytics.percentiles import (
    ComparisonContext,
    PercentileEngine,
    PercentileScope,
    PlayerMetrics,
)
from app.analytics.scoring import ScoreComponent, ScoreResult, weighted_score
from app.core import paths

REPO_ROOT = paths.REPO_ROOT
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "intelligence_scores.yaml"


class ScoreConfigError(Exception):
    """The score configuration is malformed or names something unknown."""


@dataclass(frozen=True)
class ScoreDefinition:
    """One intelligence score, as configured."""

    key: str
    label: str
    description: str
    components: dict[DerivedMetric, float]
    min_coverage: float = 1.0
    caveat: str | None = None

    @property
    def inverted_components(self) -> tuple[DerivedMetric, ...]:
        """Components whose percentile is flipped because lower is better.

        Exposed so an explanation can say so out loud rather than leaving a
        reader to wonder why a high dispossession count helped a score.
        """
        return tuple(m for m in self.components if m in LOWER_IS_BETTER)


@dataclass(frozen=True)
class IntelligenceScore:
    """A computed score with everything needed to explain it."""

    key: str
    label: str
    score: float | None
    coverage: float
    context: ComparisonContext
    components: list[ScoreComponent]
    missing: list[str]
    caveat: str | None = None

    @property
    def is_available(self) -> bool:
        return self.score is not None

    def contributions(self) -> list[tuple[str, float]]:
        """Each component's share of the final score, largest first."""
        result = ScoreResult(
            score=self.score,
            coverage=self.coverage,
            components=self.components,
            missing=self.missing,
        )
        return sorted(result.contributions(), key=lambda item: item[1], reverse=True)


def load_definitions(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, ScoreDefinition]:
    """Read and validate the score configuration.

    Validation is strict: a metric name that does not exist raises rather than
    being skipped. A silently ignored component would change every score built
    on it while leaving no trace of why.
    """
    if not path.exists():
        raise ScoreConfigError(f"Intelligence score config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    scores = raw.get("scores")
    if not isinstance(scores, dict) or not scores:
        raise ScoreConfigError(f"No scores defined in {path}")

    known = {m.value: m for m in DerivedMetric}
    definitions: dict[str, ScoreDefinition] = {}

    for key, body in scores.items():
        if not isinstance(body, dict):
            raise ScoreConfigError(f"Score '{key}' must be a mapping")

        components = body.get("components")
        if not isinstance(components, dict) or not components:
            raise ScoreConfigError(f"Score '{key}' defines no components")

        resolved: dict[DerivedMetric, float] = {}
        for metric_name, weight in components.items():
            metric = known.get(metric_name)
            if metric is None:
                raise ScoreConfigError(f"Score '{key}' references unknown metric '{metric_name}'")
            if not isinstance(weight, int | float) or weight <= 0:
                raise ScoreConfigError(
                    f"Score '{key}' component '{metric_name}' needs a positive weight"
                )
            resolved[metric] = float(weight)

        min_coverage = float(body.get("min_coverage", 1.0))
        if not 0.0 < min_coverage <= 1.0:
            raise ScoreConfigError(f"Score '{key}' min_coverage must be within (0, 1]")

        definitions[key] = ScoreDefinition(
            key=key,
            label=str(body.get("label", key)),
            description=str(body.get("description", "")).strip(),
            components=resolved,
            min_coverage=min_coverage,
            caveat=(str(body["caveat"]).strip() if body.get("caveat") else None),
        )

    return definitions


@lru_cache(maxsize=1)
def get_definitions() -> dict[str, ScoreDefinition]:
    """Cached definitions. Tests clear with `get_definitions.cache_clear()`."""
    return load_definitions()


class IntelligenceScoreEngine:
    """Computes intelligence scores for players against a percentile engine."""

    def __init__(
        self,
        percentiles: PercentileEngine,
        definitions: dict[str, ScoreDefinition] | None = None,
    ) -> None:
        self.percentiles = percentiles
        self.definitions = definitions if definitions is not None else get_definitions()

    def score(
        self,
        player: PlayerMetrics,
        key: str,
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> IntelligenceScore:
        """Compute one score for one player."""
        definition = self.definitions.get(key)
        if definition is None:
            raise ScoreConfigError(f"Unknown intelligence score: {key}")

        metrics = list(definition.components)
        ranked = self.percentiles.rank_all(
            player, metrics, scope=scope, competition_ids=competition_ids
        )

        components = [
            ScoreComponent(
                metric=metric.value,
                weight=definition.components[metric],
                # `oriented` is the higher-is-better form, so inverse metrics
                # are already flipped and weights never carry a sign.
                value=ranked[metric].oriented,
            )
            for metric in metrics
        ]
        result = weighted_score(components, min_coverage=definition.min_coverage)

        # Every component shares a context by construction: they were ranked in
        # one call with one scope and one position group.
        context = ranked[metrics[0]].context

        return IntelligenceScore(
            key=definition.key,
            label=definition.label,
            score=result.score,
            coverage=result.coverage,
            context=context,
            components=result.components,
            missing=result.missing,
            caveat=definition.caveat,
        )

    def score_all(
        self,
        player: PlayerMetrics,
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> dict[str, IntelligenceScore]:
        """Compute every configured score for one player."""
        return {
            key: self.score(player, key, scope=scope, competition_ids=competition_ids)
            for key in self.definitions
        }
