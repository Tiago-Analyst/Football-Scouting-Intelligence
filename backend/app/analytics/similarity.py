"""Statistical similarity engine.

Finds players whose statistical profile resembles a chosen player's, within a
compatible position group.

What the number is **not** (spec section 31, rule 21): the Similarity Index is
not a probability. It does not say how likely one player is to reproduce
another's output, and it knows nothing about tactical system, age curve or
temperament. `SIMILARITY_MEANING` carries that wording so it travels with the
result.

Two implementation decisions do most of the work:

**Vectors are centred before comparison.** Cosine similarity on raw percentiles
would compare vectors that all sit in the positive orthant, so every pair would
score highly and nothing would be distinguishable. Centring — percentiles about
50, z-scores about 0 — lets profiles point in genuinely different directions.

**Both representations are implemented, because the spec asks which is more
stable.** `scripts/evaluate_similarity.py` measures that rather than asserting
it; see the module docstring there for the finding.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml

from app.analytics.contracts import expires_within
from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric
from app.analytics.percentiles import PercentileEngine, PercentileScope, PlayerMetrics
from app.core import paths
from app.schemas.canonical import PositionGroup

REPO_ROOT = paths.REPO_ROOT
DEFAULT_FEATURES_PATH = REPO_ROOT / "config" / "similarity_features.yaml"

SIMILARITY_MEANING = (
    "The Statistical Similarity Index describes how closely two players' "
    "statistical profiles resemble each other on the features they share, on a "
    "0-100 scale. It is not a probability, and says nothing about quality, "
    "tactical fit or temperament. Feature Coverage is reported beside it and is "
    "not folded into it: an index of 92 over six of eleven features is a "
    "confident answer to a narrower question than the same index over eleven."
)

#: A profile needs enough present features to be worth comparing. Below this,
#: two players could agree on three metrics and differ on everything unmeasured.
#:
#: An absolute floor, kept as a backstop against a vector so short that a
#: proportion of it would still be almost nothing.
MIN_FEATURES = 5

#: And a proportional one, which is the better rule across differently sized
#: vectors.
#:
#: The outfield vectors carry eleven features and the goalkeeping one carries
#: eight. A flat floor of five therefore asked outfielders for 45% of their
#: vector and goalkeepers for 63% - the same number meaning two different
#: things, for no reason anyone chose. Requiring half of whatever the vector
#: holds asks the same question of everybody.
#:
#: The two are combined with `max`, so neither can be undercut.
MINIMUM_FEATURE_COVERAGE = 0.5


class FeatureCoverage(StrEnum):
    """How much of the intended comparison actually happened."""

    HIGH = "high"
    GOOD = "good"
    LIMITED = "limited"
    VERY_LIMITED = "very_limited"


FEATURE_COVERAGE_LABEL: dict[FeatureCoverage, str] = {
    FeatureCoverage.HIGH: "High coverage",
    FeatureCoverage.GOOD: "Good coverage",
    FeatureCoverage.LIMITED: "Limited coverage",
    FeatureCoverage.VERY_LIMITED: "Very limited coverage",
}

#: Floors, as a share of the vector the two players actually shared.
HIGH_FEATURE_COVERAGE = 0.85
GOOD_FEATURE_COVERAGE = 0.65
LIMITED_FEATURE_COVERAGE = 0.5


def classify_feature_coverage(coverage: float) -> FeatureCoverage:
    if coverage >= HIGH_FEATURE_COVERAGE:
        return FeatureCoverage.HIGH
    if coverage >= GOOD_FEATURE_COVERAGE:
        return FeatureCoverage.GOOD
    if coverage >= LIMITED_FEATURE_COVERAGE:
        return FeatureCoverage.LIMITED
    return FeatureCoverage.VERY_LIMITED

#: Below this index, a pair is not offered as similar at all.
#:
#: This is a judgement, not a measurement, and it is here rather than in the
#: caller so that no caller can forget it. An index of 0 means the two profiles
#: point in opposing directions - `to_similarity_index` says so itself - and
#: returning that as one of five "similar players" is how a list of names
#: implies a resemblance the number denies. Real data produced exactly that: a
#: midfielder whose five closest matches ran 67.8, 22.7, 6.7, 0.0, 0.0, all
#: presented alike.
#:
#: 50 is the point where a cosine of 0.5 puts the profiles 60 degrees apart -
#: sharing less of their direction than they differ on. Callers who want a
#: wider net can lower it; nobody gets it by accident.
MINIMUM_SIMILARITY = 50.0


class FeatureRepresentation(StrEnum):
    """How a player's profile is expressed before comparison."""

    PERCENTILE = "percentile"
    ZSCORE = "zscore"


class SimilarityConfigError(Exception):
    """The feature configuration is malformed or names something unknown."""


@dataclass(frozen=True)
class SimilarityCandidate:
    """A player who may be returned as similar, with the attributes filters use."""

    player_key: str
    display_name: str
    position_group: PositionGroup
    competition_id: str
    club_id: str | None = None
    age: int | None = None
    market_value_eur: int | None = None
    contract_expires: date | None = None
    nationality: str | None = None


@dataclass(frozen=True)
class SimilarityFilters:
    """Constraints on which candidates may be returned (spec section 12)."""

    min_age: int | None = None
    max_age: int | None = None
    max_market_value_eur: int | None = None
    competitions: frozenset[str] | None = None
    nationalities: frozenset[str] | None = None
    different_competition_only: bool = False
    exclude_same_club: bool = False
    younger_than_target: bool = False
    contract_expiring_within_months: int | None = None

    def allows(
        self,
        candidate: SimilarityCandidate,
        target: SimilarityCandidate,
        *,
        today: date | None = None,
    ) -> bool:
        """Whether a candidate survives every filter.

        A filter is only applied when the candidate carries the attribute it
        tests. Dropping players for *missing* data would silently narrow results
        to whoever happens to be best covered, which is a different search from
        the one the user asked for.
        """
        if self.min_age is not None and candidate.age is not None and candidate.age < self.min_age:
            return False
        if self.max_age is not None and candidate.age is not None and candidate.age > self.max_age:
            return False
        if (
            self.max_market_value_eur is not None
            and candidate.market_value_eur is not None
            and candidate.market_value_eur > self.max_market_value_eur
        ):
            return False
        if self.competitions is not None and candidate.competition_id not in self.competitions:
            return False
        if (
            self.nationalities is not None
            and candidate.nationality is not None
            and candidate.nationality not in self.nationalities
        ):
            return False
        if self.different_competition_only and candidate.competition_id == target.competition_id:
            return False
        if (
            self.exclude_same_club
            and candidate.club_id is not None
            and candidate.club_id == target.club_id
        ):
            return False
        if (
            self.younger_than_target
            and candidate.age is not None
            and target.age is not None
            and candidate.age >= target.age
        ):
            return False
        return self.contract_expiring_within_months is None or expires_within(
            candidate.contract_expires, self.contract_expiring_within_months, today=today
        )


@dataclass(frozen=True)
class SimilarityResult:
    """One similar player, with the features that made them similar."""

    candidate: SimilarityCandidate
    similarity: float
    shared_features: int
    #: How many features the position group's vector defines. `shared_features`
    #: out of this is how much of the intended comparison actually happened.
    expected_features: int = 0
    #: How comparable the two profiles are in *strength*, 0-1.
    #:
    #: Cosine measures direction, not magnitude: a player in the 90th
    #: percentile across the board points the same way as one in the 60th, so
    #: both read as highly similar. On real data this is mild - the median
    #: ratio for a top match is 0.86 - but it is not always, and a shape match
    #: between a much stronger and a much weaker player is exactly the case a
    #: recruiter must not miss. Reported rather than folded into the index, so
    #: the similarity number keeps the meaning the spec gives it.
    profile_strength_ratio: float = 1.0
    #: Per-feature absolute difference on the comparison scale, closest first.
    feature_gaps: list[tuple[str, float]] = field(default_factory=list)

    @property
    def comparable_strength(self) -> bool:
        """False when the profiles match in shape but not in level."""
        return self.profile_strength_ratio >= 0.6

    @property
    def feature_coverage(self) -> float:
        """Share of the intended vector the two players actually shared, 0-1.

        Six of eleven is much weaker evidence than eleven of eleven, and the
        similarity index alone cannot tell them apart: both can read 92. This
        is reported alongside rather than folded in, because mixing them would
        change what the index means while leaving its name and scale unchanged.
        """
        if self.expected_features <= 0:
            return 0.0
        return self.shared_features / self.expected_features

    @property
    def coverage_band(self) -> FeatureCoverage:
        return classify_feature_coverage(self.feature_coverage)

    @property
    def coverage_label(self) -> str:
        return FEATURE_COVERAGE_LABEL[self.coverage_band]

    @property
    def meaning(self) -> str:
        return SIMILARITY_MEANING


def load_feature_sets(
    path: Path = DEFAULT_FEATURES_PATH,
) -> dict[PositionGroup, tuple[DerivedMetric, ...]]:
    """Read and validate the position-specific feature vectors."""
    if not path.exists():
        raise SimilarityConfigError(f"Similarity feature config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = raw.get("position_groups")
    if not isinstance(groups, dict) or not groups:
        raise SimilarityConfigError(f"No feature vectors defined in {path}")

    known_metrics = {m.value: m for m in DerivedMetric}
    known_groups = {g.value: g for g in PositionGroup}
    resolved: dict[PositionGroup, tuple[DerivedMetric, ...]] = {}

    for name, features in groups.items():
        group = known_groups.get(str(name))
        if group is None:
            raise SimilarityConfigError(f"Unknown position group '{name}'")
        if not isinstance(features, list) or not features:
            raise SimilarityConfigError(f"Position group '{name}' has no features")

        metrics: list[DerivedMetric] = []
        for feature in features:
            metric = known_metrics.get(str(feature))
            if metric is None:
                raise SimilarityConfigError(
                    f"Position group '{name}' references unknown metric '{feature}'"
                )
            metrics.append(metric)
        if len(set(metrics)) != len(metrics):
            raise SimilarityConfigError(f"Position group '{name}' repeats a feature")
        if len(metrics) < MIN_FEATURES:
            raise SimilarityConfigError(
                f"Position group '{name}' needs at least {MIN_FEATURES} features"
            )
        resolved[group] = tuple(metrics)

    missing = set(PositionGroup) - set(resolved)
    if missing:
        raise SimilarityConfigError(
            f"No feature vector for: {', '.join(sorted(g.value for g in missing))}"
        )
    return resolved


@lru_cache(maxsize=1)
def get_feature_sets() -> dict[PositionGroup, tuple[DerivedMetric, ...]]:
    return load_feature_sets()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine of the angle between two centred vectors, -1 to 1."""
    if len(left) != len(right) or not left:
        raise ValueError("vectors must be non-empty and the same length")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        # A player exactly average on every feature has no direction to compare.
        return 0.0
    return dot / (left_norm * right_norm)


def to_similarity_index(cosine: float) -> float:
    """Map a cosine to a 0-100 index.

    Negative cosine means the two profiles point in opposing directions. That is
    "not similar", not "somewhat similar", so it maps to 0 rather than being
    stretched over the lower half of the scale — which would report two opposite
    players as 25% alike.
    """
    return max(0.0, min(1.0, cosine)) * 100.0


class SimilarityEngine:
    """Ranks players by profile resemblance within a position group."""

    def __init__(
        self,
        percentiles: PercentileEngine,
        candidates: dict[str, SimilarityCandidate],
        *,
        players: dict[str, PlayerMetrics],
        representation: FeatureRepresentation = FeatureRepresentation.PERCENTILE,
        feature_sets: dict[PositionGroup, tuple[DerivedMetric, ...]] | None = None,
        scope: PercentileScope = PercentileScope.GLOBAL,
    ) -> None:
        self.percentiles = percentiles
        self.candidates = candidates
        self.players = players
        self.representation = representation
        self.feature_sets = feature_sets if feature_sets is not None else get_feature_sets()
        # Similarity searches across leagues by default: a replacement is
        # usually being sought outside the current one.
        self.scope = scope
        self._vectors: dict[str, dict[DerivedMetric, float]] = {}

    def features_for(self, position_group: PositionGroup) -> tuple[DerivedMetric, ...]:
        return self.feature_sets[position_group]

    def _vector(self, key: str) -> dict[DerivedMetric, float]:
        """Feature vector for one player, centred so directions are comparable."""
        cached = self._vectors.get(key)
        if cached is not None:
            return cached

        record = self.players[key]
        features = self.features_for(record.position_group)
        vector: dict[DerivedMetric, float] = {}

        if self.representation is FeatureRepresentation.PERCENTILE:
            ranked = self.percentiles.rank_all(record, list(features), scope=self.scope)
            for metric in features:
                # Raw percentile, not oriented: similarity asks whether two
                # players *do the same things*, so a pair who are both
                # dispossessed constantly are alike. Orientation would make one
                # careless player resemble a careful one.
                value = ranked[metric].percentile
                if value is not None:
                    vector[metric] = value - 50.0
        else:
            for metric in features:
                value = self._zscore(record, metric)
                if value is not None:
                    vector[metric] = value

        self._vectors[key] = vector
        return vector

    def _zscore(self, record: PlayerMetrics, metric: DerivedMetric) -> float | None:
        """Standardised value within the player's position group."""
        values = self.percentiles._sorted_values(
            metric,
            record.position_group,
            record.season_id,
            None if self.scope is PercentileScope.GLOBAL else frozenset({record.competition_id}),
        )
        value = record.metrics.get(metric)
        if value is None or len(values) < 2:
            return None
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        if variance <= 0:
            return None
        return (value - mean) / math.sqrt(variance)

    def similar_to(
        self,
        target_key: str,
        *,
        filters: SimilarityFilters | None = None,
        limit: int = 20,
        minimum_minutes: int | None = None,
        minimum_similarity: float = MINIMUM_SIMILARITY,
        today: date | None = None,
    ) -> list[SimilarityResult]:
        """Rank players by resemblance to `target_key`.

        Only players in the same position group are considered: a comparison
        across positions would rank on position rather than on style.

        Returns fewer than `limit` - possibly none - when fewer players actually
        resemble the target. Filling the list to length would answer "who is
        similar to this player" with names that are not.
        """
        target = self.candidates.get(target_key)
        if target is None:
            raise KeyError(f"unknown player: {target_key}")

        target_vector = self._vector(target_key)
        if len(target_vector) < MIN_FEATURES:
            return []

        # How much of the position's intended vector a pair must share. The
        # proportion asks the same question of an eleven-feature outfield vector
        # and an eight-feature goalkeeping one; the absolute floor stops a very
        # short vector qualifying on almost nothing. Neither undercuts the other.
        expected = len(self.feature_sets.get(target.position_group, ()))
        required = max(MIN_FEATURES, math.ceil(expected * MINIMUM_FEATURE_COVERAGE))

        active = filters or SimilarityFilters()
        results: list[SimilarityResult] = []

        for key, candidate in self.candidates.items():
            if key == target_key:
                continue
            if candidate.position_group is not target.position_group:
                continue
            record = self.players.get(key)
            if record is None:
                continue
            if minimum_minutes is not None and (record.minutes or 0) < minimum_minutes:
                continue
            if not active.allows(candidate, target, today=today):
                continue

            candidate_vector = self._vector(key)
            shared = [m for m in target_vector if m in candidate_vector]
            if len(shared) < required:
                # Too little overlap to claim resemblance: the pair might agree
                # on what is measured and differ on everything that is not.
                continue

            left = [target_vector[m] for m in shared]
            right = [candidate_vector[m] for m in shared]
            index = to_similarity_index(cosine_similarity(left, right))

            left_norm = math.sqrt(sum(v * v for v in left))
            right_norm = math.sqrt(sum(v * v for v in right))
            strength_ratio = (
                min(left_norm, right_norm) / max(left_norm, right_norm)
                if max(left_norm, right_norm) > 0
                else 1.0
            )

            gaps = sorted(
                ((m.value, abs(target_vector[m] - candidate_vector[m])) for m in shared),
                key=lambda item: item[1],
            )
            results.append(
                SimilarityResult(
                    candidate=candidate,
                    similarity=index,
                    shared_features=len(shared),
                    expected_features=expected,
                    profile_strength_ratio=strength_ratio,
                    feature_gaps=gaps,
                )
            )

        results.sort(key=lambda r: r.similarity, reverse=True)
        return [r for r in results if r.similarity >= minimum_similarity][:limit]


def build_candidates(
    records: Iterable[tuple[PlayerMetrics, SimilarityCandidate]],
) -> tuple[dict[str, PlayerMetrics], dict[str, SimilarityCandidate]]:
    """Convenience: split paired records into the two lookups the engine needs."""
    players: dict[str, PlayerMetrics] = {}
    candidates: dict[str, SimilarityCandidate] = {}
    for record, candidate in records:
        players[record.player_key] = record
        candidates[record.player_key] = candidate
    return players, candidates


#: Re-exported so callers can explain why an inverse metric was not flipped.
__all__ = [
    "LOWER_IS_BETTER",
    "MIN_FEATURES",
    "SIMILARITY_MEANING",
    "FeatureRepresentation",
    "SimilarityCandidate",
    "SimilarityConfigError",
    "SimilarityEngine",
    "SimilarityFilters",
    "SimilarityResult",
    "build_candidates",
    "cosine_similarity",
    "get_feature_sets",
    "load_feature_sets",
    "to_similarity_index",
]
