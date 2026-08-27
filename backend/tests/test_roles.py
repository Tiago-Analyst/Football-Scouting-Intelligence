"""Player role engine.

The configured weights are checked against an independent transcription of the
spec, and the engine is checked for the properties that make a role score
usable: it must discriminate between archetypes, exclude roles it could not
compute rather than ranking them zero, and never present itself as quality.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analytics.intelligence import IntelligenceScoreEngine, get_definitions
from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric, DerivedMetrics
from app.analytics.percentiles import PercentileEngine, PlayerMetrics
from app.analytics.roles import (
    ROLE_SCORE_MEANING,
    RoleConfigError,
    RoleEngine,
    get_roles,
    load_roles,
)
from app.schemas.canonical import PositionGroup

SEASON = "2026-2027"

#: Transcribed from spec section 10 independently of the YAML, so a typo in
#: either surfaces as a mismatch instead of being mirrored.
SPEC_ROLES: dict[str, tuple[str, dict[str, float]]] = {
    "ball_playing_centre_back": (
        "CB",
        {
            "progressive_passes_per90": 30,
            "pass_completion": 20,
            "completed_passes_per90": 15,
            "interceptions_per90": 15,
            "duel_win_percentage": 10,
            "aerial_duel_win_percentage": 10,
        },
    ),
    "defensive_stopper": (
        "CB",
        {
            "interceptions_per90": 25,
            "successful_tackles_per90": 20,
            "blocks_per90": 15,
            "clearances_per90": 15,
            "duel_win_percentage": 15,
            "aerial_duel_win_percentage": 10,
        },
    ),
    "defensive_full_back": (
        "FB_WB",
        {
            "successful_tackles_per90": 25,
            "interceptions_per90": 20,
            "dribbled_past_per90": 20,
            "duel_win_percentage": 15,
            "progressive_passes_per90": 10,
            "aerial_duel_win_percentage": 10,
        },
    ),
    "attacking_full_back": (
        "FB_WB",
        {
            "accurate_crosses_per90": 25,
            "progressive_passes_per90": 20,
            "key_passes_per90": 15,
            "xa_per90": 15,
            "successful_dribbles_per90": 15,
            "pass_completion": 10,
        },
    ),
    "ball_winning_midfielder": (
        "DM",
        {
            "successful_tackles_per90": 25,
            "interceptions_per90": 25,
            "duel_win_percentage": 20,
            "aerial_duel_win_percentage": 10,
            "progressive_passes_per90": 10,
        },
    ),
    "deep_lying_playmaker": (
        "DM",
        {
            "progressive_passes_per90": 30,
            "completed_passes_per90": 20,
            "pass_completion": 20,
            "key_passes_per90": 10,
            "xa_per90": 10,
            "dispossessed_per90": 10,
        },
    ),
    "box_to_box_midfielder": (
        "CM",
        {
            "progressive_passes_per90": 15,
            "successful_tackles_per90": 15,
            "interceptions_per90": 15,
            "duel_win_percentage": 15,
            "successful_dribbles_per90": 10,
            "xa_per90": 10,
            "npxg_per90": 10,
            "pass_completion": 10,
        },
    ),
    "advanced_playmaker": (
        "AM",
        {
            "xa_per90": 30,
            "key_passes_per90": 25,
            "progressive_passes_per90": 15,
            "successful_dribbles_per90": 15,
            "pass_completion": 10,
            "npxg_per90": 5,
        },
    ),
    "creative_winger": (
        "WINGER",
        {
            "xa_per90": 25,
            "key_passes_per90": 20,
            "accurate_crosses_per90": 20,
            "successful_dribbles_per90": 20,
            "dribble_success_percentage": 10,
            "npxg_per90": 5,
        },
    ),
    "direct_winger": (
        "WINGER",
        {
            "successful_dribbles_per90": 25,
            "npxg_per90": 20,
            "dribble_success_percentage": 15,
            "shots_per90": 15,
            "xa_per90": 10,
            "fouls_drawn_per90": 10,
            "dispossessed_per90": 5,
        },
    ),
    "inside_forward": (
        "WINGER",
        {
            "npxg_per90": 30,
            "non_penalty_goals_per90": 25,
            "shots_per90": 15,
            "successful_dribbles_per90": 15,
            "xa_per90": 10,
            "shot_conversion": 5,
        },
    ),
    "poacher": (
        "FORWARD",
        {
            "non_penalty_goals_per90": 30,
            "npxg_per90": 30,
            "shots_on_target_per90": 15,
            "shot_conversion": 15,
            "shot_quality": 10,
        },
    ),
    "complete_forward": (
        "FORWARD",
        {
            "npxg_per90": 20,
            "non_penalty_goals_per90": 15,
            "xa_per90": 15,
            "key_passes_per90": 10,
            "duel_win_percentage": 10,
            "aerial_duel_win_percentage": 10,
            "successful_dribbles_per90": 10,
            "pass_completion": 5,
            "fouls_drawn_per90": 5,
        },
    ),
    "target_forward": (
        "FORWARD",
        {
            "aerial_duel_win_percentage": 25,
            "aerial_duels_won_per90": 20,
            "npxg_per90": 20,
            "duel_win_percentage": 15,
            "fouls_drawn_per90": 10,
            "key_passes_per90": 5,
            "xa_per90": 5,
        },
    ),
    "shot_stopper": (
        "GK",
        {
            "save_percentage": 45,
            "inside_box_saves_per90": 20,
            "goals_conceded_per90": 20,
            "saves_per90": 15,
        },
    ),
}

#: The one role the spec builds from an intelligence score rather than a metric.
SPEC_SCORE_COMPONENTS = {"ball_winning_midfielder": {"ball_security": 10}}


def player(
    key: str,
    *,
    group: PositionGroup = PositionGroup.DM,
    competition: str = "c1",
    minutes: int = 2000,
    **metrics: float,
) -> PlayerMetrics:
    return PlayerMetrics(
        player_key=key,
        position_group=group,
        competition_id=competition,
        season_id=SEASON,
        metrics=DerivedMetrics(minutes=minutes, **metrics),  # type: ignore[arg-type]
    )


DM_METRICS = [
    "progressive_passes_per90",
    "completed_passes_per90",
    "pass_completion",
    "key_passes_per90",
    "xa_per90",
    "dispossessed_per90",
    "successful_tackles_per90",
    "interceptions_per90",
    "duel_win_percentage",
    "aerial_duel_win_percentage",
    "dribble_success_percentage",
]


def dm_cohort(count: int = 20) -> list[PlayerMetrics]:
    """A cohort varying across every metric the DM roles need."""
    return [player(f"p{i}", **{name: float(i) for name in DM_METRICS}) for i in range(count)]


def engine_for(population: list[PlayerMetrics]) -> RoleEngine:
    percentiles = PercentileEngine(population)
    return RoleEngine(IntelligenceScoreEngine(percentiles, get_definitions()))


class TestConfiguration:
    def test_all_fifteen_roles_are_defined(self) -> None:
        assert len(get_roles()) == 15

    def test_configured_metric_weights_match_the_specification(self) -> None:
        roles = get_roles()
        for key, (_, expected) in SPEC_ROLES.items():
            assert key in roles, f"missing role: {key}"
            actual = {m.value: w for m, w in roles[key].metric_weights.items()}
            assert actual == expected, key

    def test_score_components_match_the_specification(self) -> None:
        """Only the Ball-Winning Midfielder is built partly from an
        intelligence score; nothing else should have acquired one."""
        roles = get_roles()
        for key, role in roles.items():
            assert role.score_weights == SPEC_SCORE_COMPONENTS.get(key, {}), key

    def test_every_role_weights_sum_to_one_hundred(self) -> None:
        for key, role in get_roles().items():
            total = sum(role.metric_weights.values()) + sum(role.score_weights.values())
            assert total == pytest.approx(100.0), key

    def test_each_role_primary_position_matches_the_specification(self) -> None:
        roles = get_roles()
        for key, (expected_group, _) in SPEC_ROLES.items():
            assert roles[key].primary_position.value == expected_group, key

    def test_every_position_group_has_at_least_one_role(self) -> None:
        """A group with no role would leave that cohort without a best role."""
        covered = {g for role in get_roles().values() for g in role.position_groups}
        assert covered == set(PositionGroup)

    def test_inverse_components_are_plain_metrics_in_config(self) -> None:
        """The spec calls these 'Inverse ...'. Orientation is automatic, so
        listing an inverse metric would flip them twice."""
        roles = get_roles()
        assert roles["defensive_full_back"].inverted_metrics == (DerivedMetric.DRIBBLED_PAST_PER90,)
        assert DerivedMetric.DISPOSSESSED_PER90 in roles["deep_lying_playmaker"].metric_weights
        assert DerivedMetric.GOALS_CONCEDED_PER90 in LOWER_IS_BETTER

    def test_the_goalkeeper_role_carries_its_team_context_caveat(self) -> None:
        """The spec forbids inferring elite shot-stopping from these figures."""
        caveat = get_roles()["shot_stopper"].caveat
        assert caveat
        assert "post-shot" in caveat.lower()


class TestConfigValidation:
    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "roles.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_unknown_metric_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            "roles:\n  r:\n    position_groups: [CM]\n    components:\n"
            "      metrics:\n        nope: 100\n",
        )
        with pytest.raises(RoleConfigError, match="unknown metric"):
            load_roles(path)

    def test_unknown_intelligence_score_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            "roles:\n  r:\n    position_groups: [CM]\n    components:\n"
            "      scores:\n        not_a_score: 100\n",
        )
        with pytest.raises(RoleConfigError, match="unknown intelligence score"):
            load_roles(path, known_scores={"ball_security"})

    def test_unknown_position_group_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            "roles:\n  r:\n    position_groups: [SWEEPER]\n    components:\n"
            "      metrics:\n        goals_per90: 100\n",
        )
        with pytest.raises(RoleConfigError, match="unknown position group"):
            load_roles(path)

    def test_a_role_without_position_groups_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            "roles:\n  r:\n    components:\n      metrics:\n        goals_per90: 100\n",
        )
        with pytest.raises(RoleConfigError, match="position group"):
            load_roles(path)

    def test_a_role_without_components_is_rejected(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "roles:\n  r:\n    position_groups: [CM]\n")
        with pytest.raises(RoleConfigError, match="no components"):
            load_roles(path)

    def test_a_missing_file_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RoleConfigError, match="not found"):
            load_roles(tmp_path / "nope.yaml")


class TestCompatibility:
    def test_a_player_is_only_scored_against_roles_for_their_position(self) -> None:
        engine = engine_for(dm_cohort())
        keys = {r.key for r in engine.compatible_roles(PositionGroup.GK)}
        assert keys == {"shot_stopper"}

    def test_a_defensive_midfielder_gets_several_compatible_roles(self) -> None:
        """Section 11 requires alternatives to be shown, which needs more than
        one compatible role."""
        engine = engine_for(dm_cohort())
        keys = {r.key for r in engine.compatible_roles(PositionGroup.DM)}
        assert {"deep_lying_playmaker", "ball_winning_midfielder"} <= keys
        assert len(keys) >= 2

    def test_a_player_without_a_position_group_has_no_roles(self) -> None:
        engine = engine_for(dm_cohort())
        assert engine.compatible_roles(None) == []


class TestScoring:
    def test_a_top_ranked_player_scores_highly(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        result = engine.score(population[-1], "deep_lying_playmaker")
        assert result.score is not None
        assert result.score > 80

    def test_scores_stay_within_range(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        for record in population:
            result = engine.score(record, "deep_lying_playmaker")
            if result.score is not None:
                assert 0.0 <= result.score <= 100.0

    def test_an_unknown_role_raises(self) -> None:
        engine = engine_for(dm_cohort())
        with pytest.raises(RoleConfigError, match="Unknown role"):
            engine.score(dm_cohort()[0], "not_a_role")

    def test_a_role_built_on_an_intelligence_score_computes(self) -> None:
        """Ball-Winning Midfielder weights Ball Security at 10%, so the role
        engine has to resolve a whole composite score as one component."""
        population = dm_cohort()
        engine = engine_for(population)
        result = engine.score(population[-1], "ball_winning_midfielder")
        assert result.score is not None
        assert any(c.metric == "score:ball_security" for c in result.components)


class TestArchetypesSeparate:
    def test_a_passer_and_a_tackler_get_different_best_roles(self) -> None:
        """If every profile produced the same best role, the engine would be
        ranking noise."""
        base = {name: 10.0 for name in DM_METRICS}
        population = [player(f"p{i}", **{n: float(i) for n in DM_METRICS}) for i in range(20)]

        passer = player(
            "passer",
            **{
                **base,
                "progressive_passes_per90": 19.0,
                "completed_passes_per90": 19.0,
                "pass_completion": 19.0,
                "successful_tackles_per90": 0.0,
                "interceptions_per90": 0.0,
                "duel_win_percentage": 0.0,
            },
        )
        tackler = player(
            "tackler",
            **{
                **base,
                "progressive_passes_per90": 0.0,
                "completed_passes_per90": 0.0,
                "pass_completion": 0.0,
                "successful_tackles_per90": 19.0,
                "interceptions_per90": 19.0,
                "duel_win_percentage": 19.0,
            },
        )
        engine = engine_for(population)

        passer_fit = engine.fit(passer)
        tackler_fit = engine.fit(tackler)
        assert passer_fit.best is not None and tackler_fit.best is not None
        assert passer_fit.best.key == "deep_lying_playmaker"
        assert tackler_fit.best.key == "ball_winning_midfielder"


class TestRoleFit:
    def test_the_best_role_is_the_highest_scoring(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        fit = engine.fit(population[-1])
        assert fit.best is not None
        for alternative in fit.alternatives:
            assert (alternative.score or 0) <= (fit.best.score or 0)

    def test_alternatives_are_ordered_downwards(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        scores = [s.score or 0 for s in engine.fit(population[-1]).all_scores]
        assert scores == sorted(scores, reverse=True)

    def test_uncomputable_roles_are_excluded_not_scored_zero(self) -> None:
        """An absent score means unknown fit. Ranking it zero would push a
        player away from a role they might well suit."""
        population = dm_cohort()
        engine = engine_for(population)
        fit = engine.fit(population[-1])
        assert all(s.score is not None for s in fit.all_scores)

    def test_a_player_with_no_computable_role_has_no_best(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        empty = player("empty", group=PositionGroup.DM)
        fit = engine.fit(empty)
        assert fit.best is None
        assert fit.alternatives == []

    def test_the_meaning_of_the_score_travels_with_the_fit(self) -> None:
        """Rules 20 and 21: never presented as quality or probability."""
        engine = engine_for(dm_cohort())
        fit = engine.fit(dm_cohort()[-1])
        assert fit.meaning == ROLE_SCORE_MEANING
        assert "not player quality" in fit.meaning
        assert "not a probability" in fit.meaning


class TestExplainability:
    def test_a_role_score_decomposes_to_its_total(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        result = engine.score(population[-1], "deep_lying_playmaker")
        assert result.score is not None
        assert sum(v for _, v in result.contributions()) == pytest.approx(result.score)

    def test_the_comparison_context_travels_with_the_score(self) -> None:
        population = dm_cohort()
        engine = engine_for(population)
        result = engine.score(population[-1], "deep_lying_playmaker")
        assert result.context.position_group is PositionGroup.DM
        assert result.context.population_size == 20


class TestAgainstTheMockDataset:
    def test_every_player_gets_a_best_role_or_an_honest_gap(self) -> None:
        from app.analytics.metrics import compute_derived
        from app.providers.mock import SEASON_ID, MockPerformanceProvider

        provider = MockPerformanceProvider(competitions=1, clubs_per_competition=10)
        players = provider.get_players("mock-comp-01", SEASON_ID)
        groups = {p.source_player_id: p.position_group for p in players}
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
        engine = engine_for(population)

        with_best = 0
        for record in population[:150]:
            fit = engine.fit(record)
            if fit.best is not None:
                assert 0.0 <= (fit.best.score or 0.0) <= 100.0
                with_best += 1
        assert with_best > 100
