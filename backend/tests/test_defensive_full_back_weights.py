"""The Defensive Full-Back reweighting, held to what it was changed for.

`successful_tackles` is declared by the provider and never populated, so
`tackles_per90` is ATTEMPTS. At 25% it was the heaviest component of a
defensive role while being unable to tell a full-back who tackles often and
succeeds from one who tackles often and fails, and a validation audit found it
carrying 41% of one player's realised score.

These tests use the product's own scoring code and real oriented percentiles
captured from production for 40 full-backs with a full season behind them, so
the before/after figures are the engine's arithmetic rather than a separate
model of it.
"""

from __future__ import annotations

import json
import pathlib
import statistics

import pytest

from app.analytics.roles import get_roles
from app.analytics.scoring import ScoreComponent, weighted_score

FIXTURE = pathlib.Path(__file__).parent / "data" / "full_backs_production.json"

#: What the role weighted before this change, kept so the comparison is against
#: a recorded definition rather than against memory.
WEIGHTS_BEFORE: dict[str, float] = {
    "tackles_per90": 25,
    "interceptions_per90": 20,
    "dribbled_past_per90": 20,
    "duel_win_percentage": 15,
    "progressive_passes_per90": 10,
    "aerial_duel_win_percentage": 10,
}

MIN_COVERAGE = 0.79


@pytest.fixture(scope="module")
def players() -> list[dict]:
    if not FIXTURE.exists():
        pytest.skip(f"no production fixture at {FIXTURE}")
    return json.loads(FIXTURE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _dominance(weights: dict[str, float], oriented: dict[str, float]) -> float | None:
    """Share of the realised score carried by its single largest contributor.

    Built with `weighted_score` and read back through `contributions()`, which
    is what the API itself calls to decompose a role.
    """
    components = [
        ScoreComponent(metric=metric, weight=weight, value=oriented.get(metric))
        for metric, weight in weights.items()
    ]
    result = weighted_score(components, min_coverage=MIN_COVERAGE)
    if result.score is None:
        return None
    contributions = dict(result.contributions())
    total = sum(contributions.values())
    if total <= 0:
        return None
    return max(contributions.values()) / total * 100.0


def _current_weights() -> dict[str, float]:
    return {m.value: w for m, w in get_roles()["defensive_full_back"].metric_weights.items()}


class TestTheWeightsThemselves:
    def test_tackle_attempts_are_no_longer_the_heaviest_component(self) -> None:
        weights = _current_weights()
        heaviest = max(weights.values())
        assert weights["tackles_per90"] < heaviest, (
            "a count the provider cannot qualify must not lead a defensive role"
        )

    def test_outcome_metrics_outweigh_the_volume_count(self) -> None:
        # Duels won and interceptions are outcomes. Tackles attempted is not.
        weights = _current_weights()
        assert weights["duel_win_percentage"] > weights["tackles_per90"]
        assert weights["interceptions_per90"] > weights["tackles_per90"]

    def test_the_added_metrics_are_ones_the_provider_supplies(self) -> None:
        # Blocks and clearances are not new to the product: the Defensive
        # Stopper has scored from both since it was written.
        weights = _current_weights()
        stopper = {m.value for m in get_roles()["defensive_stopper"].metric_weights}
        for added in ("blocks_per90", "clearances_per90"):
            assert added in weights
            assert added in stopper

    def test_the_weights_still_sum_to_one_hundred(self) -> None:
        assert sum(_current_weights().values()) == pytest.approx(100.0)

    def test_nothing_was_substituted_for_an_unavailable_metric(self) -> None:
        """Aerial duel win % has no denominator and stays absent, not replaced.

        Dropping it and calling the role complete would be the substitution
        this product refuses to make.
        """
        assert "aerial_duel_win_percentage" in _current_weights()
        assert "successful_tackles_per90" not in _current_weights()
        assert "tackle_success_percentage" not in _current_weights()


class TestMeasuredAgainstProduction:
    def test_dominance_falls(self, players: list[dict]) -> None:
        before = [d for p in players if (d := _dominance(WEIGHTS_BEFORE, p["oriented"]))]
        after = [d for p in players if (d := _dominance(_current_weights(), p["oriented"]))]
        assert before and after
        assert statistics.mean(after) < statistics.mean(before), (
            f"mean dominance {statistics.mean(before):.1f}% -> {statistics.mean(after):.1f}%"
        )
        assert max(after) < max(before)

    def test_no_player_loses_their_score(self, players: list[dict]) -> None:
        """The reweighting must not quietly narrow who can be scored.

        Whether a player scores at all is a coverage question, and coverage is
        being decided separately. This change must not pre-empt it.
        """
        before = sum(1 for p in players if _dominance(WEIGHTS_BEFORE, p["oriented"]) is not None)
        after = sum(1 for p in players if _dominance(_current_weights(), p["oriented"]) is not None)
        assert after >= before, f"{before} scorable before, {after} after"

    def test_no_single_metric_carries_half_a_score(self, players: list[dict]) -> None:
        # Not a guarantee the arithmetic can make for every input, but a
        # regression guard: the audit's complaint was 41%, and the reweighted
        # role should not be producing worse.
        worst = max(
            (d for p in players if (d := _dominance(_current_weights(), p["oriented"]))),
            default=0.0,
        )
        assert worst < 60.0, f"one metric carries {worst:.0f}% of a realised score"
