"""Statistical similarity engine.

Covers exactly what spec section 12 asks to be validated — identical vectors,
near-identical vectors, cross-position behaviour, filtering and the index range
— plus the two traps that make a similarity engine look like it works while
ranking noise: uncentred vectors, and comparing players who share almost no
measured features.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.analytics.metrics import DerivedMetric, DerivedMetrics
from app.analytics.percentiles import PercentileEngine, PlayerMetrics
from app.analytics.similarity import (
    MIN_FEATURES,
    SIMILARITY_MEANING,
    FeatureRepresentation,
    SimilarityCandidate,
    SimilarityConfigError,
    SimilarityEngine,
    SimilarityFilters,
    cosine_similarity,
    get_feature_sets,
    load_feature_sets,
    to_similarity_index,
)
from app.schemas.canonical import PositionGroup

SEASON = "2026-2027"

#: The midfield features the spec states verbatim (section 12).
SPEC_MIDFIELD_FEATURES = [
    "progressive_passes_per90",
    "completed_passes_per90",
    "pass_completion",
    "key_passes_per90",
    "xa_per90",
    "successful_dribbles_per90",
    "tackles_per90",
    "interceptions_per90",
    "duel_win_percentage",
    "aerial_duel_win_percentage",
    "dispossessed_per90",
]


def metrics_for(values: dict[str, float], minutes: int = 2000) -> DerivedMetrics:
    return DerivedMetrics(minutes=minutes, **values)  # type: ignore[arg-type]


def make_player(
    key: str,
    values: dict[str, float],
    *,
    group: PositionGroup = PositionGroup.CM,
    competition: str = "c1",
    club: str = "club1",
    minutes: int = 2000,
    age: int | None = 25,
    market_value: int | None = 5_000_000,
    contract: date | None = None,
    nationality: str | None = "Portugal",
) -> tuple[PlayerMetrics, SimilarityCandidate]:
    record = PlayerMetrics(
        player_key=key,
        position_group=group,
        competition_id=competition,
        season_id=SEASON,
        metrics=metrics_for(values, minutes),
    )
    candidate = SimilarityCandidate(
        player_key=key,
        display_name=key,
        position_group=group,
        competition_id=competition,
        club_id=club,
        age=age,
        market_value_eur=market_value,
        contract_expires=contract,
        nationality=nationality,
    )
    return record, candidate


def build_engine(
    entries: list[tuple[PlayerMetrics, SimilarityCandidate]],
    representation: FeatureRepresentation = FeatureRepresentation.PERCENTILE,
) -> SimilarityEngine:
    players = {r.player_key: r for r, _ in entries}
    candidates = {c.player_key: c for _, c in entries}
    percentiles = PercentileEngine(list(players.values()))
    return SimilarityEngine(percentiles, candidates, players=players, representation=representation)


def varied_cohort(count: int = 30) -> list[tuple[PlayerMetrics, SimilarityCandidate]]:
    """A cohort whose features vary *independently*.

    Setting every feature to the same value would make all profile vectors
    parallel, and cosine similarity would then rate every pair 100 - which says
    something true about cosine but nothing about the engine. Real players are
    strong in some areas and weak in others, so the features are rotated to
    produce genuinely different directions.
    """
    entries = []
    for i in range(count):
        values = {
            name: float((i * (index + 3)) % 29) for index, name in enumerate(SPEC_MIDFIELD_FEATURES)
        }
        entries.append(make_player(f"p{i}", values))
    return entries


class TestConfiguration:
    def test_the_midfield_vector_matches_the_specification(self) -> None:
        features = get_feature_sets()[PositionGroup.CM]
        assert [m.value for m in features] == SPEC_MIDFIELD_FEATURES

    def test_every_position_group_has_a_vector(self) -> None:
        """A group without one would leave that cohort unable to be compared."""
        assert set(get_feature_sets()) == set(PositionGroup)

    def test_every_vector_has_enough_features(self) -> None:
        for group, features in get_feature_sets().items():
            assert len(features) >= MIN_FEATURES, group

    def test_unknown_metric_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "features.yaml"
        path.write_text("position_groups:\n  CM:\n    - not_a_metric\n", encoding="utf-8")
        with pytest.raises(SimilarityConfigError, match="unknown metric"):
            load_feature_sets(path)

    def test_a_missing_position_group_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "features.yaml"
        path.write_text(
            "position_groups:\n  CM:\n" + "".join(f"    - {m}\n" for m in SPEC_MIDFIELD_FEATURES),
            encoding="utf-8",
        )
        with pytest.raises(SimilarityConfigError, match="No feature vector for"):
            load_feature_sets(path)

    def test_a_repeated_feature_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "features.yaml"
        path.write_text(
            "position_groups:\n  CM:\n    - goals_per90\n    - goals_per90\n", encoding="utf-8"
        )
        with pytest.raises(SimilarityConfigError, match="repeats a feature"):
            load_feature_sets(path)


class TestCosine:
    def test_identical_vectors_are_perfectly_similar(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_opposite_vectors_are_perfectly_dissimilar(self) -> None:
        assert cosine_similarity([1.0, 2.0], [-1.0, -2.0]) == pytest.approx(-1.0)

    def test_orthogonal_vectors_score_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_a_zero_vector_has_no_direction(self) -> None:
        """A player exactly average on every feature points nowhere, so there is
        nothing to compare rather than a perfect match."""
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_mismatched_lengths_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            cosine_similarity([1.0], [1.0, 2.0])


class TestSimilarityIndex:
    def test_identical_maps_to_one_hundred(self) -> None:
        assert to_similarity_index(1.0) == 100.0

    def test_opposed_profiles_map_to_zero_not_the_midpoint(self) -> None:
        """Stretching negative cosine across the lower half would report two
        opposite players as 25% alike."""
        assert to_similarity_index(-1.0) == 0.0
        assert to_similarity_index(-0.5) == 0.0

    def test_orthogonal_maps_to_zero(self) -> None:
        assert to_similarity_index(0.0) == 0.0

    def test_the_index_stays_within_range(self) -> None:
        for cosine in (-2.0, -1.0, 0.0, 0.5, 1.0, 2.0):
            assert 0.0 <= to_similarity_index(cosine) <= 100.0


class TestIdenticalAndNearIdentical:
    @staticmethod
    def _values_of(entries, key: str) -> dict[str, float]:
        record = next(r for r, _ in entries if r.player_key == key)
        return {
            name: record.metrics.get(DerivedMetric(name)) or 0.0 for name in SPEC_MIDFIELD_FEATURES
        }

    def test_an_identical_profile_scores_one_hundred(self) -> None:
        entries = varied_cohort()
        clone_values = self._values_of(entries, "p10")
        entries.append(make_player("clone", clone_values, club="other"))
        engine = build_engine(entries)

        results = engine.similar_to("p10", limit=5)
        assert results
        assert results[0].candidate.player_key == "clone"
        assert results[0].similarity == pytest.approx(100.0)
        assert results[0].profile_strength_ratio == pytest.approx(1.0)

    def test_a_near_identical_profile_scores_very_highly(self) -> None:
        entries = varied_cohort()
        nudged = {name: value + 0.2 for name, value in self._values_of(entries, "p10").items()}
        entries.append(make_player("nudged", nudged, club="other"))
        engine = build_engine(entries)

        results = engine.similar_to("p10", limit=5)
        assert results[0].candidate.player_key == "nudged"
        assert results[0].similarity > 95.0

    def test_an_opposed_profile_ranks_last(self) -> None:
        base = {name: 5.0 for name in SPEC_MIDFIELD_FEATURES}
        opposite = dict(base)
        for index, name in enumerate(SPEC_MIDFIELD_FEATURES):
            opposite[name] = 29.0 if index % 2 == 0 else 0.0
            base[name] = 0.0 if index % 2 == 0 else 29.0

        entries = varied_cohort()
        entries.append(make_player("mirror_a", base, club="a"))
        entries.append(make_player("mirror_b", opposite, club="b"))
        engine = build_engine(entries)

        results = engine.similar_to("mirror_a", limit=40)
        ranked = {r.candidate.player_key: r.similarity for r in results}
        assert ranked.get("mirror_b", 0.0) < 25.0


class TestPositionBehaviour:
    def test_players_from_another_position_are_never_returned(self) -> None:
        """Comparing across positions would rank on position, not on style."""
        entries = varied_cohort()
        for i in range(15):
            entries.append(
                make_player(
                    f"cb{i}",
                    {
                        "progressive_passes_per90": float(i),
                        "completed_passes_per90": float(i),
                        "pass_completion": float(i),
                        "tackles_per90": float(i),
                        "interceptions_per90": float(i),
                        "blocks_per90": float(i),
                        "clearances_per90": float(i),
                        "duel_win_percentage": float(i),
                        "aerial_duel_win_percentage": float(i),
                        "aerial_duels_per90": float(i),
                        "dribbled_past_per90": float(i),
                    },
                    group=PositionGroup.CB,
                )
            )
        engine = build_engine(entries)
        results = engine.similar_to("p10", limit=50)
        assert results
        assert all(r.candidate.position_group is PositionGroup.CM for r in results)

    def test_each_position_uses_its_own_feature_vector(self) -> None:
        engine = build_engine(varied_cohort())
        assert engine.features_for(PositionGroup.CB) != engine.features_for(PositionGroup.WINGER)
        assert DerivedMetric.CLEARANCES_PER90 in engine.features_for(PositionGroup.CB)

    def test_the_target_is_never_returned_as_similar_to_itself(self) -> None:
        engine = build_engine(varied_cohort())
        results = engine.similar_to("p10", limit=50)
        assert all(r.candidate.player_key != "p10" for r in results)


class TestFiltering:
    @pytest.fixture
    def engine(self) -> SimilarityEngine:
        entries = varied_cohort()
        values = {name: 10.0 for name in SPEC_MIDFIELD_FEATURES}
        entries.append(
            make_player(
                "young_cheap",
                values,
                club="c2",
                competition="c2",
                age=20,
                market_value=1_000_000,
                contract=date(2027, 6, 30),
                nationality="Spain",
            )
        )
        entries.append(
            make_player(
                "old_costly",
                values,
                club="club1",
                competition="c1",
                age=33,
                market_value=40_000_000,
                contract=date(2031, 6, 30),
                nationality="Brazil",
            )
        )
        return build_engine(entries)

    def test_maximum_age_excludes_older_players(self, engine: SimilarityEngine) -> None:
        keys = {
            r.candidate.player_key
            for r in engine.similar_to("p10", filters=SimilarityFilters(max_age=25), limit=50)
        }
        assert "young_cheap" in keys
        assert "old_costly" not in keys

    def test_minimum_age_excludes_younger_players(self, engine: SimilarityEngine) -> None:
        keys = {
            r.candidate.player_key
            for r in engine.similar_to("p10", filters=SimilarityFilters(min_age=30), limit=50)
        }
        assert "old_costly" in keys
        assert "young_cheap" not in keys

    def test_maximum_market_value_excludes_expensive_players(
        self, engine: SimilarityEngine
    ) -> None:
        keys = {
            r.candidate.player_key
            for r in engine.similar_to(
                "p10", filters=SimilarityFilters(max_market_value_eur=5_000_000), limit=50
            )
        }
        assert "young_cheap" in keys
        assert "old_costly" not in keys

    def test_competition_filter_restricts_the_pool(self, engine: SimilarityEngine) -> None:
        results = engine.similar_to(
            "p10", filters=SimilarityFilters(competitions=frozenset({"c2"})), limit=50
        )
        assert results
        assert all(r.candidate.competition_id == "c2" for r in results)

    def test_different_competition_only_excludes_the_targets_league(
        self, engine: SimilarityEngine
    ) -> None:
        results = engine.similar_to(
            "p10", filters=SimilarityFilters(different_competition_only=True), limit=50
        )
        assert results
        assert all(r.candidate.competition_id != "c1" for r in results)

    def test_exclude_same_club_drops_team_mates(self, engine: SimilarityEngine) -> None:
        results = engine.similar_to(
            "p10", filters=SimilarityFilters(exclude_same_club=True), limit=50
        )
        assert all(r.candidate.club_id != "club1" for r in results)

    def test_younger_than_target_uses_the_targets_age(self, engine: SimilarityEngine) -> None:
        results = engine.similar_to(
            "p10", filters=SimilarityFilters(younger_than_target=True), limit=50
        )
        assert results
        assert all((r.candidate.age or 99) < 25 for r in results)

    def test_contract_filter_keeps_only_expiring_deals(self, engine: SimilarityEngine) -> None:
        results = engine.similar_to(
            "p10",
            filters=SimilarityFilters(contract_expiring_within_months=18),
            limit=50,
            today=date(2026, 8, 1),
        )
        keys = {r.candidate.player_key for r in results}
        assert "young_cheap" in keys
        assert "old_costly" not in keys

    def test_nationality_filter_restricts_the_pool(self, engine: SimilarityEngine) -> None:
        results = engine.similar_to(
            "p10", filters=SimilarityFilters(nationalities=frozenset({"Spain"})), limit=50
        )
        assert results
        assert all(r.candidate.nationality == "Spain" for r in results)

    def test_minimum_minutes_excludes_small_samples(self) -> None:
        entries = varied_cohort()
        values = {name: 10.0 for name in SPEC_MIDFIELD_FEATURES}
        entries.append(make_player("fringe", values, club="c9", minutes=200))
        engine = build_engine(entries)
        keys = {
            r.candidate.player_key for r in engine.similar_to("p10", limit=50, minimum_minutes=900)
        }
        assert "fringe" not in keys

    def test_filters_do_not_drop_players_for_missing_attributes(self) -> None:
        """Dropping unknowns would narrow results to whoever is best covered,
        which is a different search from the one asked for."""
        entries = varied_cohort()
        values = {name: 10.0 for name in SPEC_MIDFIELD_FEATURES}
        entries.append(make_player("unknown_age", values, club="c3", age=None))
        engine = build_engine(entries)
        keys = {
            r.candidate.player_key
            for r in engine.similar_to("p10", filters=SimilarityFilters(max_age=22), limit=50)
        }
        assert "unknown_age" in keys


class TestRangeAndOutput:
    def test_every_similarity_is_within_range(self) -> None:
        engine = build_engine(varied_cohort())
        for result in engine.similar_to("p10", limit=50):
            assert 0.0 <= result.similarity <= 100.0

    def test_results_are_ordered_most_similar_first(self) -> None:
        engine = build_engine(varied_cohort())
        scores = [r.similarity for r in engine.similar_to("p10", limit=50)]
        assert scores == sorted(scores, reverse=True)

    def test_the_limit_is_respected(self) -> None:
        engine = build_engine(varied_cohort())
        assert len(engine.similar_to("p10", limit=3)) == 3

    def test_results_report_how_many_features_were_shared(self) -> None:
        engine = build_engine(varied_cohort())
        for result in engine.similar_to("p10", limit=5):
            assert result.shared_features >= MIN_FEATURES

    def test_feature_gaps_explain_the_match(self) -> None:
        """Section 12 results have to be interpretable, not just ordered."""
        engine = build_engine(varied_cohort())
        result = engine.similar_to("p10", limit=1)[0]
        assert result.feature_gaps
        gaps = [gap for _, gap in result.feature_gaps]
        assert gaps == sorted(gaps)

    def test_the_meaning_travels_with_the_result(self) -> None:
        """Rule 21: never described as a probability."""
        engine = build_engine(varied_cohort())
        result = engine.similar_to("p10", limit=1)[0]
        assert result.meaning == SIMILARITY_MEANING
        assert "not a probability" in result.meaning

    def test_an_unknown_target_raises(self) -> None:
        engine = build_engine(varied_cohort())
        with pytest.raises(KeyError, match="unknown player"):
            engine.similar_to("nobody")

    def test_a_player_with_too_few_features_returns_nothing(self) -> None:
        entries = varied_cohort()
        entries.append(make_player("sparse", {"goals_per90": 1.0}, club="c8"))
        engine = build_engine(entries)
        assert engine.similar_to("sparse") == []


class TestRepresentations:
    @pytest.mark.parametrize("representation", list(FeatureRepresentation))
    def test_both_representations_recognise_an_identical_profile(
        self, representation: FeatureRepresentation
    ) -> None:
        entries = varied_cohort()
        source = next(r for r, _ in entries if r.player_key == "p10")
        clone_values = {
            name: source.metrics.get(DerivedMetric(name)) or 0.0 for name in SPEC_MIDFIELD_FEATURES
        }
        entries.append(make_player("clone", clone_values, club="other"))
        engine = build_engine(entries, representation)
        results = engine.similar_to("p10", limit=3)
        assert results[0].candidate.player_key == "clone"
        assert results[0].similarity > 95.0

    def test_cosine_ignores_magnitude_so_strength_is_reported_separately(self) -> None:
        """Two players with the same shape but different levels are rated
        highly similar by cosine. That is a property of the measure the spec
        chose, not a bug - so the strength ratio is reported alongside, and
        flags the pair as not comparable in level."""
        entries = varied_cohort()
        strong = {name: 26.0 for name in SPEC_MIDFIELD_FEATURES}
        weak = {name: 16.0 for name in SPEC_MIDFIELD_FEATURES}
        entries.append(make_player("strong", strong, club="s"))
        entries.append(make_player("weak", weak, club="w"))
        engine = build_engine(entries)

        match = next(
            r for r in engine.similar_to("strong", limit=50) if r.candidate.player_key == "weak"
        )
        assert match.similarity > 90.0
        assert match.profile_strength_ratio < 0.9
        assert match.comparable_strength is not None

    def test_vectors_are_centred_so_profiles_can_oppose(self) -> None:
        """Uncentred percentiles all sit in the positive orthant, so every pair
        would score highly and nothing would be distinguishable."""
        engine = build_engine(varied_cohort())
        results = engine.similar_to("p0", limit=40)
        assert min(r.similarity for r in results) < 50.0


class TestAgainstTheMockDataset:
    def test_similarity_behaves_across_a_real_cohort(self) -> None:
        from app.analytics.metrics import compute_derived
        from app.providers.mock import SEASON_ID, MockPerformanceProvider

        provider = MockPerformanceProvider(competitions=1, clubs_per_competition=12)
        squad = provider.get_players("mock-comp-01", SEASON_ID)
        groups = {p.source_player_id: p.position_group for p in squad}
        names = {p.source_player_id: p.full_name for p in squad}

        players: dict[str, PlayerMetrics] = {}
        candidates: dict[str, SimilarityCandidate] = {}
        for record in provider.get_competition_stats("mock-comp-01", SEASON_ID):
            key = record.source_player_id
            players[key] = PlayerMetrics(
                player_key=key,
                position_group=groups[key],
                competition_id=record.competition_id,
                season_id=record.season_id,
                metrics=compute_derived(record),
            )
            candidates[key] = SimilarityCandidate(
                player_key=key,
                display_name=names[key],
                position_group=groups[key],
                competition_id=record.competition_id,
            )

        engine = SimilarityEngine(
            PercentileEngine(list(players.values())), candidates, players=players
        )
        target = next(
            k
            for k, r in players.items()
            if r.position_group is PositionGroup.CM and (r.minutes or 0) >= 900
        )
        results = engine.similar_to(target, limit=10, minimum_minutes=900)
        assert results
        assert all(r.candidate.position_group is PositionGroup.CM for r in results)
        assert all(0.0 <= r.similarity <= 100.0 for r in results)
        # A real cohort should produce a genuine ranking, not a flat list.
        assert results[0].similarity - results[-1].similarity > 1.0
