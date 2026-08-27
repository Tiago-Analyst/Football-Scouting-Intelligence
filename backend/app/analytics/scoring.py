"""Score utilities: inversion, weighting and coverage.

Composite scores in this product are built from **percentiles, never from raw
metrics** (spec section 9). That is not a stylistic preference: progressive
passes per 90 runs about 0 to 12 while pass completion runs 0 to 100, so
weighting the raw values would let one metric dominate a score purely because
of its unit. Converting each component to a 0-100 percentile first puts them on
one scale before any weight is applied.

Two things this module refuses to do quietly:

- **Compute a score from a partial component set.** If a component is missing,
  the default is no score rather than a score built from what happened to be
  available. A number that looks comparable but was computed from different
  inputs for different players is worse than a gap.
- **Return a score without its provenance.** Every result carries the component
  values it used and the share of weight they covered, so a score can always be
  decomposed and explained.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCORE_MIN = 0.0
SCORE_MAX = 100.0


def clamp_score(value: float) -> float:
    """Hold a score inside 0-100.

    Section 24 requires scores to stay in range. Rounding and floating-point
    drift can otherwise produce 100.0000001, which then fails a database check
    constraint at load time.
    """
    return max(SCORE_MIN, min(SCORE_MAX, value))


def invert_percentile(percentile: float | None) -> float | None:
    """Flip a percentile so that a low raw value ranks well.

    For metrics where less is better - being dispossessed, being dribbled past,
    conceding - a player in the 10th percentile for the raw metric is in the
    90th for the underlying quality. Inverting here means a high component
    score always reads as good, so weights never need to carry a sign.

    Absence propagates: an unknown percentile inverts to unknown, not to 100.
    """
    if percentile is None:
        return None
    return clamp_score(SCORE_MAX - clamp_score(percentile))


@dataclass(frozen=True)
class ScoreComponent:
    """One weighted input to a composite score."""

    metric: str
    weight: float
    #: Percentile on a 0-100 scale, or None when it could not be computed.
    value: float | None = None

    @property
    def is_available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class ScoreResult:
    """A composite score together with everything needed to explain it."""

    score: float | None
    coverage: float
    components: list[ScoreComponent] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        return self.score is not None

    def contributions(self) -> list[tuple[str, float]]:
        """How much each component added to the final score.

        Weights are renormalised over the components that were present, so the
        contributions sum to the score itself and a ranking can be justified
        line by line.
        """
        available = [c for c in self.components if c.is_available]
        total_weight = sum(c.weight for c in available)
        if not total_weight:
            return []
        return [(c.metric, (c.weight / total_weight) * (c.value or 0.0)) for c in available]


def weighted_score(components: list[ScoreComponent], *, min_coverage: float = 1.0) -> ScoreResult:
    """Combine percentile components into a single 0-100 score.

    `min_coverage` is the share of total weight that must be present. It
    defaults to 1.0 - every component required - so a score is never quietly
    built from a subset. Lower it only where a documented decision says a
    partial score is still meaningful; the coverage travels with the result
    either way so the UI can qualify what it shows.

    Weights are renormalised across the components that are present. Without
    that, a missing 20% component would drag every score down by a fifth and
    look like poor performance rather than absent data.
    """
    if not components:
        return ScoreResult(score=None, coverage=0.0, components=[], missing=[])

    total_weight = sum(c.weight for c in components)
    if total_weight <= 0:
        raise ValueError("component weights must sum to a positive number")

    available = [c for c in components if c.is_available]
    missing = [c.metric for c in components if not c.is_available]
    coverage = sum(c.weight for c in available) / total_weight

    if coverage < min_coverage or not available:
        return ScoreResult(
            score=None, coverage=coverage, components=list(components), missing=missing
        )

    available_weight = sum(c.weight for c in available)
    raw = sum((c.weight / available_weight) * clamp_score(c.value or 0.0) for c in available)

    return ScoreResult(
        score=clamp_score(raw),
        coverage=coverage,
        components=list(components),
        missing=missing,
    )


def normalise_weights(weights: dict[str, float]) -> dict[str, float]:
    """Scale weights so they sum to 1.0.

    Configuration files express weights as percentages that should add to 100,
    but a hand-edited file often does not quite. Normalising makes the score
    independent of that, so a typo shifts relative emphasis rather than
    silently rescaling every score in the system.
    """
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return {name: weight / total for name, weight in weights.items()}
