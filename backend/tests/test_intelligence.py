"""Intelligence score engine.

Two things matter beyond the arithmetic: the configured weights must match the
specification exactly, and a score must never appear when its inputs did not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analytics.intelligence import (
    IntelligenceScoreEngine,
    ScoreConfigError,
    get_definitions,
    load_definitions,
)
from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric, DerivedMetrics
from app.analytics.percentiles import PercentileEngine, PercentileScope, PlayerMetrics
from app.schemas.canonical import PositionGroup

SEASON = "2026-2027"

#: The weights the master spec (section 9) states, transcribed independently of
#: the configuration file so a typo in either is caught rather than mirrored.
SPEC_WEIGHTS: dict[str, dict[str, float]] = {
    "ball_progression": {
        "progressive_passes_per90": 45,
        "completed_passes_per90": 20,
        "key_passes_per90": 15,
        "successful_dribbles_per90": 20,
    },
    "ball_security": {
        "pass_completion": 45,
        "dribble_success_percentage": 20,
        "dispossessed_per90": 25,
        "completed_passes_per90": 10,
    },
    "chance_creation": {
        "xa_per90": 40,
        "key_passes_per90": 35,
        "accurate_crosses_per90": 15,
        "assists_per90": 10,
    },
    "defensive_activity": {
        "successful_tackles_per90": 35,
        "interceptions_per90": 35,
        "blocks_per90": 15,
        "duels_won_per90": 15,
    },
    "duel_dominance": {
        "duel_win_percentage": 50,
        "aerial_duel_win_percentage": 30,
        "duels_won_per90": 20,
    },
    "one_v_one_threat": {
        "successful_dribbles_per90": 50,
        "dribble_success_percentage": 30,
        "fouls_drawn_per90": 20,
    },
    "goal_threat": {
        "npxg_per90": 35,
        "shots_per90": 25,
        "shots_on_target_per90": 20,
        "successful_dribbles_per90": 10,
        "xa_per90": 10,
    },
    "finishing": {
        "non_penalty_goals_per90": 35,
        "npxg_per90": 20,
        "shot_conversion": 20,
        "shot_accuracy": 15,
        "shot_quality": 10,
    },
}


#: Metrics the specification names that the provider does not supply, and what
#: is used in their place. Every entry is a declared deviation carrying a caveat
#: on the score itself - see docs/methodology.md. Adding one here without the
#: caveat is caught by the test below.
DECLARED_SUBSTITUTIONS = {"successful_tackles_per90": "tackles_per90"}


def player(key: str, *, minutes: int = 2000, **metrics: float) -> PlayerMetrics:
    return PlayerMetrics(
        player_key=key,
        position_group=PositionGroup.CM,
        competition_id="c1",
        season_id=SEASON,
        metrics=DerivedMetrics(minutes=minutes, **metrics),  # type: ignore[arg-type]
    )


def spread(metric: str, count: int = 20) -> list[PlayerMetrics]:
    """A cohort spanning 0..count-1 on one metric, for predictable percentiles."""
    return [player(f"p{i}", **{metric: float(i)}) for i in range(count)]


class TestConfiguration:
    def test_the_configured_weights_match_the_specification(self) -> None:
        """Transcribed from the spec separately; a typo in the YAML shows here.

        One deviation is allowed and named: the specification weights
        `successful_tackles_per90`, which FootyStats declares and never
        populates, so Defensive Activity could be produced for nobody. The
        substitution is listed here rather than written into `SPEC_WEIGHTS`, so
        the transcription still says what the specification says and any *other*
        divergence still fails.
        """
        definitions = get_definitions()
        for key, expected in SPEC_WEIGHTS.items():
            assert key in definitions, f"missing score: {key}"
            actual = {m.value: w for m, w in definitions[key].components.items()}
            assert actual == {
                DECLARED_SUBSTITUTIONS.get(metric, metric): weight
                for metric, weight in expected.items()
            }, key

    def test_the_substituted_score_says_so_on_every_figure(self) -> None:
        """A deviation nobody is told about is the substitution the project
        forbids. The caveat travels with the score to the page."""
        caveat = get_definitions()["defensive_activity"].caveat
        assert caveat
        assert "attempted" in caveat.lower()
        assert "not tackles won" in caveat.lower()

    def test_every_configured_score_is_one_the_spec_defines(self) -> None:
        """Guards against a score being added to config without a definition
        behind it."""
        assert set(get_definitions()) == set(SPEC_WEIGHTS)

    def test_weights_within_each_score_sum_to_one_hundred(self) -> None:
        for key, definition in get_definitions().items():
            assert sum(definition.components.values()) == pytest.approx(100.0), key

    def test_every_component_is_a_real_metric(self) -> None:
        known = {m.value for m in DerivedMetric}
        for definition in get_definitions().values():
            for metric in definition.components:
                assert metric.value in known

    def test_finishing_carries_its_noise_caveat(self) -> None:
        """The spec forbids presenting finishing as objective ability, so the
        warning has to travel with the score."""
        finishing = get_definitions()["finishing"]
        assert finishing.caveat
        assert "regress" in finishing.caveat.lower()

    def test_ball_security_inverts_dispossession(self) -> None:
        """The spec calls this component 'Inverse Dispossessed /90'. It is the
        plain metric in config because orientation is automatic; double
        inverting would make losing the ball a virtue."""
        definition = get_definitions()["ball_security"]
        assert DerivedMetric.DISPOSSESSED_PER90 in definition.components
        assert definition.inverted_components == (DerivedMetric.DISPOSSESSED_PER90,)
        assert DerivedMetric.DISPOSSESSED_PER90 in LOWER_IS_BETTER


class TestConfigValidation:
    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "scores.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_an_unknown_metric_is_rejected(self, tmp_path: Path) -> None:
        """Skipping it silently would change every score built on it and leave
        no trace of why."""
        path = self._write(
            tmp_path,
            "scores:\n  x:\n    components:\n      not_a_real_metric: 100\n",
        )
        with pytest.raises(ScoreConfigError, match="unknown metric"):
            load_definitions(path)

    def test_a_score_without_components_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "scores:\n  x:\n    label: X\n")
        with pytest.raises(ScoreConfigError, match="no components"):
            load_definitions(path)

    def test_a_non_positive_weight_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "scores:\n  x:\n    components:\n      goals_per90: 0\n")
        with pytest.raises(ScoreConfigError, match="positive weight"):
            load_definitions(path)

    def test_an_out_of_range_coverage_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            "scores:\n  x:\n    min_coverage: 1.5\n    components:\n      goals_per90: 100\n",
        )
        with pytest.raises(ScoreConfigError, match="min_coverage"):
            load_definitions(path)

    def test_a_missing_file_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ScoreConfigError, match="not found"):
            load_definitions(tmp_path / "nope.yaml")

    def test_an_empty_file_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "version: 1\n")
        with pytest.raises(ScoreConfigError, match="No scores"):
            load_definitions(path)


class TestScoring:
    def test_a_top_ranked_player_scores_near_one_hundred(self) -> None:
        population = [
            player(
                f"p{i}",
                progressive_passes_per90=float(i),
                completed_passes_per90=float(i),
                key_passes_per90=float(i),
                successful_dribbles_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        best = population[-1]
        result = engine.score(best, "ball_progression")
        assert result.score is not None
        assert result.score > 95

    def test_a_bottom_ranked_player_scores_near_zero(self) -> None:
        population = [
            player(
                f"p{i}",
                progressive_passes_per90=float(i),
                completed_passes_per90=float(i),
                key_passes_per90=float(i),
                successful_dribbles_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        result = engine.score(population[0], "ball_progression")
        assert result.score is not None
        assert result.score < 5

    def test_weights_actually_shift_the_result(self) -> None:
        """A player elite on the 45% component and poor on the rest must beat
        one with the reverse profile."""
        population = [
            player(
                f"p{i}",
                progressive_passes_per90=float(i),
                completed_passes_per90=float(i),
                key_passes_per90=float(i),
                successful_dribbles_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))

        progressor = player(
            "progressor",
            progressive_passes_per90=19.0,
            completed_passes_per90=0.0,
            key_passes_per90=0.0,
            successful_dribbles_per90=0.0,
        )
        dribbler = player(
            "dribbler",
            progressive_passes_per90=0.0,
            completed_passes_per90=0.0,
            key_passes_per90=0.0,
            successful_dribbles_per90=19.0,
        )
        progressor_score = engine.score(progressor, "ball_progression").score
        dribbler_score = engine.score(dribbler, "ball_progression").score
        assert progressor_score is not None and dribbler_score is not None
        assert progressor_score > dribbler_score

    def test_scores_stay_within_range(self) -> None:
        population = spread("progressive_passes_per90")
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        for record in population:
            result = engine.score(record, "ball_progression")
            if result.score is not None:
                assert 0.0 <= result.score <= 100.0


class TestInversion:
    def test_losing_the_ball_less_scores_better(self) -> None:
        """The whole point of the inverse component: a player dispossessed
        rarely must score above one dispossessed constantly."""
        population = [
            player(
                f"p{i}",
                pass_completion=80.0,
                dribble_success_percentage=50.0,
                completed_passes_per90=40.0,
                dispossessed_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        careful = engine.score(population[0], "ball_security").score
        careless = engine.score(population[-1], "ball_security").score
        assert careful is not None and careless is not None
        assert careful > careless


class TestAvailability:
    def test_a_missing_component_disables_the_score(self) -> None:
        """Strict by default: a score built from a subset is not comparable
        with one built from the full set."""
        population = spread("progressive_passes_per90")
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        result = engine.score(population[-1], "ball_progression")
        assert result.score is None
        assert set(result.missing) >= {"completed_passes_per90", "key_passes_per90"}

    def test_coverage_is_reported_even_when_the_score_is_withheld(self) -> None:
        population = spread("progressive_passes_per90")
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        result = engine.score(population[-1], "ball_progression")
        assert 0.0 < result.coverage < 1.0

    def test_an_unknown_score_key_raises(self) -> None:
        engine = IntelligenceScoreEngine(PercentileEngine(spread("goals_per90")))
        with pytest.raises(ScoreConfigError, match="Unknown intelligence score"):
            engine.score(player("t", goals_per90=1.0), "not_a_score")


class TestExplainability:
    def test_the_score_decomposes_into_its_components(self) -> None:
        """Section 13: every recommendation must be explainable."""
        population = [
            player(
                f"p{i}",
                progressive_passes_per90=float(i),
                completed_passes_per90=float(i),
                key_passes_per90=float(i),
                successful_dribbles_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        result = engine.score(population[-1], "ball_progression")

        assert result.score is not None
        contributions = result.contributions()
        assert len(contributions) == 4
        assert sum(value for _, value in contributions) == pytest.approx(result.score)

    def test_contributions_are_ordered_by_size(self) -> None:
        population = [
            player(
                f"p{i}",
                progressive_passes_per90=float(i),
                completed_passes_per90=float(i),
                key_passes_per90=float(i),
                successful_dribbles_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        values = [v for _, v in engine.score(population[-1], "ball_progression").contributions()]
        assert values == sorted(values, reverse=True)

    def test_the_comparison_context_travels_with_the_score(self) -> None:
        population = [
            player(
                f"p{i}",
                progressive_passes_per90=float(i),
                completed_passes_per90=float(i),
                key_passes_per90=float(i),
                successful_dribbles_per90=float(i),
            )
            for i in range(20)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))
        result = engine.score(population[-1], "ball_progression")
        assert result.context.position_group is PositionGroup.CM
        assert result.context.population_size == 20


class TestScopes:
    def test_scores_can_be_computed_globally(self) -> None:
        weak = [
            PlayerMetrics(
                player_key=f"w{i}",
                position_group=PositionGroup.CM,
                competition_id="weak",
                season_id=SEASON,
                metrics=DerivedMetrics(
                    minutes=2000,
                    progressive_passes_per90=1.0,
                    completed_passes_per90=1.0,
                    key_passes_per90=1.0,
                    successful_dribbles_per90=1.0,
                ),
            )
            for i in range(15)
        ]
        strong = [
            PlayerMetrics(
                player_key=f"s{i}",
                position_group=PositionGroup.CM,
                competition_id="strong",
                season_id=SEASON,
                metrics=DerivedMetrics(
                    minutes=2000,
                    progressive_passes_per90=9.0,
                    completed_passes_per90=9.0,
                    key_passes_per90=9.0,
                    successful_dribbles_per90=9.0,
                ),
            )
            for i in range(15)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(weak + strong))

        local = engine.score(weak[0], "ball_progression")
        globally = engine.score(weak[0], "ball_progression", scope=PercentileScope.GLOBAL)
        assert local.score is not None and globally.score is not None
        # Mid-pack at home, bottom half once the stronger league is included.
        assert globally.score < local.score
        assert globally.context.caveat is not None


class TestAgainstTheMockDataset:
    def test_every_score_computes_across_a_real_cohort(self) -> None:
        from app.analytics.metrics import compute_derived
        from app.providers.mock import SEASON_ID, MockPerformanceProvider

        provider = MockPerformanceProvider(competitions=1, clubs_per_competition=10)
        groups = {
            p.source_player_id: p.position_group
            for p in provider.get_players("mock-comp-01", SEASON_ID)
        }
        population = [
            PlayerMetrics(
                player_key=r.source_player_id,
                position_group=groups[r.source_player_id],
                competition_id=r.competition_id,
                season_id=r.season_id,
                metrics=compute_derived(r),
            )
            for r in provider.get_competition_stats("mock-comp-01", SEASON_ID)
        ]
        engine = IntelligenceScoreEngine(PercentileEngine(population))

        produced = 0
        for record in population[:120]:
            for result in engine.score_all(record).values():
                if result.score is not None:
                    assert 0.0 <= result.score <= 100.0
                    produced += 1
        assert produced > 0
