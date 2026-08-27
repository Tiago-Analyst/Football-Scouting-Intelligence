"""Canonical model guarantees.

The two invariants worth protecting: absent is distinguishable from zero, and
impossible values cannot enter the model at all.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.canonical import (
    GOALKEEPER_METRICS,
    OUTFIELD_METRICS,
    CanonicalMetric,
    PlayerSeasonStats,
    ProviderInfo,
)

IDENTITY_FIELDS = {"source_player_id", "season_id", "competition_id", "club_id"}


def stats(**overrides: object) -> PlayerSeasonStats:
    base: dict[str, object] = {
        "source_player_id": "p1",
        "season_id": "2026-2027",
        "competition_id": "c1",
        "club_id": "club1",
    }
    base.update(overrides)
    return PlayerSeasonStats(**base)  # type: ignore[arg-type]


class TestMetricEnumStaysInSync:
    def test_enum_covers_exactly_the_model_metric_fields(self) -> None:
        """A metric added to the model but not the enum would be invisible to
        availability checks, and a provider could never declare it."""
        model_metrics = set(PlayerSeasonStats.model_fields) - IDENTITY_FIELDS
        enum_metrics = {m.value for m in CanonicalMetric}
        assert model_metrics == enum_metrics

    def test_goalkeeper_and_outfield_partition_every_metric(self) -> None:
        assert frozenset(CanonicalMetric) == GOALKEEPER_METRICS | OUTFIELD_METRICS
        assert not (GOALKEEPER_METRICS & OUTFIELD_METRICS)

    def test_every_metric_is_readable_by_enum(self) -> None:
        record = stats()
        for metric in CanonicalMetric:
            assert record.get(metric) is None


class TestAbsentIsNotZero:
    def test_unsupplied_metric_reads_as_none(self) -> None:
        assert stats().get(CanonicalMetric.TACKLES) is None

    def test_genuine_zero_reads_as_zero(self) -> None:
        """A player who made no tackles is not the same as a provider that does
        not report tackles. Conflating them would fabricate a data point."""
        assert stats(tackles=0).get(CanonicalMetric.TACKLES) == 0.0

    def test_supplied_metrics_excludes_absent_and_includes_zero(self) -> None:
        record = stats(tackles=0, interceptions=5)
        supplied = record.supplied_metrics()
        assert CanonicalMetric.TACKLES in supplied
        assert CanonicalMetric.INTERCEPTIONS in supplied
        assert CanonicalMetric.BLOCKS not in supplied


class TestImpossibleValuesAreRejected:
    @pytest.mark.parametrize(
        "field", ["minutes", "goals", "shots", "tackles", "xg", "npxg", "xa", "saves"]
    )
    def test_negative_values_raise(self, field: str) -> None:
        """A provider sentinel such as -1 for 'unknown' must fail loudly rather
        than enter a percentile distribution."""
        with pytest.raises(ValidationError):
            stats(**{field: -1})

    def test_implausible_height_raises(self) -> None:
        from app.schemas.canonical import PlayerIdentity, PositionGroup

        with pytest.raises(ValidationError):
            PlayerIdentity(
                source_player_id="p",
                full_name="Test",
                raw_position="CM",
                position_group=PositionGroup.CM,
                club_id="c",
                competition_id="comp",
                height_cm=45,
            )


class TestConsistencyErrors:
    def test_clean_record_reports_nothing(self) -> None:
        record = stats(
            appearances=30,
            starts=28,
            minutes=2500,
            passes=1500,
            passes_completed=1300,
            shots=40,
            shots_on_target=18,
            goals=9,
            non_penalty_goals=8,
            duels=300,
            duels_won=160,
            aerial_duels=90,
            aerial_duels_won=50,
            xg=9.4,
            npxg=8.6,
        )
        assert record.consistency_errors() == []

    @pytest.mark.parametrize(
        ("overrides", "fragment"),
        [
            ({"passes": 100, "passes_completed": 120}, "passes_completed"),
            ({"shots": 10, "shots_on_target": 12}, "shots_on_target"),
            ({"duels": 50, "duels_won": 60}, "duels_won"),
            ({"aerial_duels": 10, "aerial_duels_won": 11}, "aerial_duels_won"),
            ({"duels": 10, "aerial_duels": 20}, "aerial_duels"),
            ({"goals": 10, "non_penalty_goals": 12}, "non_penalty_goals"),
            ({"xg": 5.0, "npxg": 6.0}, "npxg"),
            ({"appearances": 2, "starts": 3}, "starts"),
            ({"tackles": 5, "successful_tackles": 6}, "successful_tackles"),
        ],
    )
    def test_subset_violations_are_reported(
        self, overrides: dict[str, object], fragment: str
    ) -> None:
        problems = stats(**overrides).consistency_errors()
        assert any(fragment in p for p in problems), problems

    def test_goals_cannot_exceed_shots_on_target(self) -> None:
        problems = stats(shots=20, shots_on_target=5, goals=9).consistency_errors()
        assert any("goals" in p and "shots_on_target" in p for p in problems)

    def test_minutes_cannot_exceed_time_available(self) -> None:
        problems = stats(appearances=2, minutes=900).consistency_errors()
        assert any("minutes" in p for p in problems)

    def test_absent_values_cannot_contradict(self) -> None:
        """An unknown value must not be treated as zero and reported as a
        violation - that would flag every partially-supplied record."""
        assert stats(passes_completed=500).consistency_errors() == []
        assert stats(passes=500).consistency_errors() == []


class TestProviderInfo:
    def test_supports_reflects_declared_metrics(self) -> None:
        info = ProviderInfo(
            name="X",
            is_mock=True,
            validated=False,
            available_metrics=frozenset({CanonicalMetric.TACKLES}),
        )
        assert info.supports(CanonicalMetric.TACKLES)
        assert not info.supports(CanonicalMetric.INTERCEPTIONS)

    def test_missing_from_lists_unsatisfied_requirements(self) -> None:
        """This is what lets a score be disabled instead of computed from a
        partial input set and presented as comparable."""
        info = ProviderInfo(
            name="X",
            is_mock=True,
            validated=False,
            available_metrics=frozenset({CanonicalMetric.TACKLES}),
        )
        required = frozenset({CanonicalMetric.TACKLES, CanonicalMetric.INTERCEPTIONS})
        assert info.missing_from(required) == frozenset({CanonicalMetric.INTERCEPTIONS})

    def test_nothing_satisfied_returns_everything_required(self) -> None:
        info = ProviderInfo(name="X", is_mock=True, validated=False, available_metrics=frozenset())
        required = frozenset({CanonicalMetric.XA})
        assert info.missing_from(required) == required
