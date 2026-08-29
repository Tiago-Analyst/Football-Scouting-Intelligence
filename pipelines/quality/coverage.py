"""Which metrics the loaded data actually carries, and what is lost without them.

The specification's rule is that an absent metric disables the feature that
needs it rather than being quietly replaced. Honouring that requires knowing two
things: which canonical metrics are actually populated, and what depends on each
one.

The second is the interesting half. Rather than re-declaring the dependency
graph — which would drift from `compute_derived` the first time somebody edited
it — this module **measures** it: build a stats record with every field
populated, blank one field, and see which derived metrics turn to None. That is
the real dependency, discovered from the code that implements it.

Intelligence scores and roles then follow from their configuration, which
already declares its components.

Nothing here writes to the database. `pipelines/quality/report.py` runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.intelligence import get_definitions
from app.analytics.metrics import DerivedMetric, compute_derived
from app.analytics.roles import get_roles
from app.models import DimPlayer, FactPlayerSeasonStats
from app.schemas.canonical import CanonicalMetric, PlayerSeasonStats

#: Values used to build the probe record. Any positive number works; they only
#: have to be present and to keep the model's own consistency rules satisfied
#: (completed passes not above attempted, and so on).
_PROBE_TOTAL = 100
_PROBE_MINUTES = 2000


@dataclass(frozen=True)
class MetricCoverage:
    """How much of one canonical metric the loaded data actually has.

    Coverage is judged **within a position group**, not across the squad. The
    first version of this check judged overall coverage and reported saves,
    clean sheets and goals conceded as sparse at 12% — which is not a data
    problem, it is the share of players who are goalkeepers. A check that cries
    wolf on correct data trains people to ignore it.
    """

    metric: CanonicalMetric
    rows: int
    populated: int
    #: The position group where this metric is best covered, and its coverage
    #: there. For a position-specific metric that is the group it belongs to.
    best_group: str | None = None
    best_group_coverage: float = 0.0

    @property
    def coverage(self) -> float:
        return self.populated / self.rows if self.rows else 0.0

    @property
    def is_position_specific(self) -> bool:
        """Well covered somewhere, largely absent overall."""
        return self.best_group_coverage >= 0.95 and self.coverage < 0.5

    @property
    def status(self) -> str:
        """`absent` is the one that matters: the provider does not supply this.

        A metric at 0% everywhere is not a data problem to be chased. It is a
        statement about the source, and everything downstream of it must be
        switched off.
        """
        if self.rows == 0:
            return "unknown"
        if self.populated == 0:
            return "absent"
        if self.is_position_specific:
            return "position_specific"
        # Judged where the metric belongs. A metric complete among the players
        # who can have it is complete, whatever its share of the whole squad.
        effective = max(self.coverage, self.best_group_coverage)
        if effective < 0.5:
            return "sparse"
        if effective < 0.95:
            return "partial"
        return "complete"


@dataclass(frozen=True)
class Impact:
    """What becomes uncomputable when a set of metrics is absent."""

    derived_metrics: frozenset[DerivedMetric]
    scores: frozenset[str]
    roles: frozenset[str]


def _probe_stats(
    *, omit: CanonicalMetric | None = None, omit_all: set[CanonicalMetric] | None = None
) -> PlayerSeasonStats:
    """A fully-populated stats record, optionally missing one field or several.

    Ratios use a smaller numerator than denominator so that a record with every
    field set still satisfies the model's consistency rules — completed passes
    cannot exceed attempted, and a record that violated that would be rejected
    before it could be probed.
    """
    #: Fields that must not exceed their paired total.
    subsets = {
        CanonicalMetric.PASSES_COMPLETED,
        CanonicalMetric.SHOTS_ON_TARGET,
        CanonicalMetric.DUELS_WON,
        CanonicalMetric.AERIAL_DUELS_WON,
        CanonicalMetric.NON_PENALTY_GOALS,
        CanonicalMetric.SUCCESSFUL_DRIBBLES,
        CanonicalMetric.SUCCESSFUL_TACKLES,
        CanonicalMetric.ACCURATE_CROSSES,
        CanonicalMetric.PROGRESSIVE_PASSES,
        CanonicalMetric.KEY_PASSES,
        CanonicalMetric.SAVES,
    }

    excluded = set(omit_all or ())
    if omit is not None:
        excluded.add(omit)

    values: dict[str, int] = {}
    for metric in CanonicalMetric:
        if metric in excluded:
            continue
        if metric is CanonicalMetric.MINUTES:
            values[metric.value] = _PROBE_MINUTES
        elif metric is CanonicalMetric.APPEARANCES:
            values[metric.value] = 30
        elif metric is CanonicalMetric.STARTS:
            values[metric.value] = 25
        elif metric is CanonicalMetric.PENALTIES_TAKEN:
            # Must stay well below `shots`. Set equal to it, non-penalty shots
            # became zero, `shot_conversion` and `shot_quality` divided by zero
            # and came back None from the *baseline* probe - so the measurement
            # concluded nothing depended on them at all, and their inputs went
            # unreported in the impact analysis.
            values[metric.value] = 5
        else:
            values[metric.value] = _PROBE_TOTAL // 2 if metric in subsets else _PROBE_TOTAL

    return PlayerSeasonStats(
        source_player_id="probe",
        season_id="probe",
        competition_id="probe",
        club_id="probe",
        **values,  # type: ignore[arg-type]
    )


def _computed(stats: PlayerSeasonStats) -> frozenset[DerivedMetric]:
    derived = compute_derived(stats)
    return frozenset(
        metric for metric in DerivedMetric if getattr(derived, metric.value, None) is not None
    )


@lru_cache(maxsize=1)
def dependency_map() -> dict[CanonicalMetric, frozenset[DerivedMetric]]:
    """Which derived metrics each canonical metric is required for.

    Measured, not declared: blank one field on a fully-populated record and see
    what stops computing. A metric that nothing depends on maps to an empty set,
    which is itself worth knowing — it means nothing downstream would notice its
    absence.
    """
    baseline = _computed(_probe_stats())
    return {metric: baseline - _computed(_probe_stats(omit=metric)) for metric in CanonicalMetric}


def impact_of_absence(absent: set[CanonicalMetric]) -> Impact:
    """What cannot be computed if these canonical metrics are missing.

    Measured by blanking the whole set at once, not by combining the
    per-metric results of `dependency_map`.

    The difference is not academic. `minutes` and `recorded_minutes` are a
    fallback pair: the metrics engine uses the second where a provider supplies
    it and the first otherwise, so blanking either alone costs nothing. Union
    the two individual answers and you conclude that losing both costs nothing
    — the opposite of true, since without any minutes no per-90 exists at all.

    One-at-a-time measurement cannot see a dependency that only breaks when
    several fields go together. Measuring the actual set can.

    A score or role is lost when *any* required component is lost, because both
    engines default to `min_coverage = 1.0` — a score is never quietly built
    from whichever components happened to survive.
    """
    if not absent:
        return Impact(frozenset(), frozenset(), frozenset())

    baseline = _computed(_probe_stats())
    remaining = _computed(_probe_stats(omit_all=absent))
    lost_derived: set[DerivedMetric] = set(baseline - remaining)

    # A score or role survives when the weight that remains still meets its own
    # `min_coverage`. Treating every definition as requiring the full 100% would
    # over-report: a role that documents which component it can do without, and
    # renormalises the rest, is not lost when that component goes.
    def survives(weights: dict[object, float], lost: set[object], floor: float) -> bool:
        total = sum(weights.values())
        if total <= 0:
            return False
        remaining = sum(w for component, w in weights.items() if component not in lost)
        return remaining / total >= floor

    lost_scores = {
        key
        for key, definition in get_definitions().items()
        if not survives(dict(definition.components), set(lost_derived), definition.min_coverage)
    }

    lost_roles = set()
    for role in get_roles().values():
        weights: dict[object, float] = {
            **{m: w for m, w in role.metric_weights.items()},
            **{s: w for s, w in role.score_weights.items()},
        }
        unavailable: set[object] = set(lost_derived) | set(lost_scores)
        if not survives(weights, unavailable, role.min_coverage):
            lost_roles.add(role.key)

    return Impact(
        derived_metrics=frozenset(lost_derived),
        scores=frozenset(lost_scores),
        roles=frozenset(lost_roles),
    )


def metric_coverage(session: Session, *, source: str | None = None) -> list[MetricCoverage]:
    """Count populated values per canonical metric in `fact_player_season_stats`.

    Two queries — one overall, one grouped by position — rather than one per
    metric. Thirty-eight round trips to answer a single question would make this
    report too slow to run routinely, and a report nobody runs is not a control.
    """
    columns = [
        func.count(getattr(FactPlayerSeasonStats, metric.value)).label(metric.value)
        for metric in CanonicalMetric
    ]

    overall = select(func.count().label("rows"), *columns)
    if source is not None:
        overall = overall.where(FactPlayerSeasonStats.source == source)
    mapping = session.execute(overall).one()._mapping
    rows = int(mapping["rows"])

    grouped = (
        select(DimPlayer.position_group.label("grp"), func.count().label("rows"), *columns)
        .join(DimPlayer, FactPlayerSeasonStats.player_id == DimPlayer.player_id)
        .where(DimPlayer.position_group.is_not(None))
        .group_by(DimPlayer.position_group)
    )
    if source is not None:
        grouped = grouped.where(FactPlayerSeasonStats.source == source)

    # Per metric, the position group that covers it best.
    best: dict[str, tuple[str | None, float]] = {m.value: (None, 0.0) for m in CanonicalMetric}
    for group_row in session.execute(grouped).all():
        group_map = group_row._mapping
        group_rows = int(group_map["rows"])
        if group_rows == 0:
            continue
        for metric in CanonicalMetric:
            share = int(group_map[metric.value]) / group_rows
            if share > best[metric.value][1]:
                best[metric.value] = (str(group_map["grp"]), share)

    return [
        MetricCoverage(
            metric=metric,
            rows=rows,
            populated=int(mapping[metric.value]),
            best_group=best[metric.value][0],
            best_group_coverage=best[metric.value][1],
        )
        for metric in CanonicalMetric
    ]


def absent_metrics(coverage: list[MetricCoverage]) -> set[CanonicalMetric]:
    return {item.metric for item in coverage if item.status == "absent"}
