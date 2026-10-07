"""When a role turns out to be a ranking of one metric.

Weights say what a role intends to measure. Contributions say what it ended up
measuring for a particular player, and the two diverge: a 30% component on a
percentile of 95 contributes more than a 40% one on a percentile of 20. A
validation audit found an Advanced Playmaker whose xA alone produced 44% of
his realised score - a role named for creation behaving like an xA ranking,
and nothing on the page said so.

Explanatory, never punitive. Nothing is reweighted, no score changes, and no
player is ranked differently because of it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.percentiles import ComparisonContext, PercentileScope
from app.analytics.roles import RoleScore
from app.analytics.scoring import ScoreComponent
from app.api.v1.players import DOMINANT_CONTRIBUTION, _dominant
from app.schemas.canonical import PositionGroup

CONTEXT = ComparisonContext(
    scope=PercentileScope.COMPETITION,
    position_group=PositionGroup.CM,
    season_id="2026-2027",
    competition_ids=("c1",),
    population_size=40,
    minimum_minutes=0,
)


def score_with(components: list[tuple[str, float, float | None]]) -> RoleScore:
    return RoleScore(
        key="advanced_playmaker",
        label="Advanced Playmaker",
        score=70.0,
        coverage=1.0,
        context=CONTEXT,
        components=[ScoreComponent(metric=m, weight=w, value=v) for m, w, v in components],
        missing=[],
    )


class TestNamingIt:
    def test_an_evenly_spread_score_names_nothing(self) -> None:
        even = score_with([(f"m{i}", 25.0, 60.0) for i in range(4)])
        assert _dominant(even) == (None, None)

    def test_a_score_carried_by_one_metric_names_it(self) -> None:
        lopsided = score_with(
            [
                ("xa_per90", 30.0, 95.0),
                ("key_passes_per90", 25.0, 20.0),
                ("pass_completion", 25.0, 15.0),
                ("npxg_per90", 20.0, 10.0),
            ]
        )
        label, share = _dominant(lopsided)
        assert label is not None
        assert "xA" in label
        assert share is not None and share >= DOMINANT_CONTRIBUTION

    def test_it_reads_realised_contribution_not_configured_weight(self) -> None:
        """The heaviest weight is not always the biggest contributor.

        A 20% component on a high percentile can outproduce a 45% one on a low
        percentile, and the reader is unknowingly ranking by the first.
        """
        weights_say_one_thing = score_with(
            [("heavy_but_low", 70.0, 5.0), ("light_but_high", 30.0, 99.0)]
        )
        label, _ = _dominant(weights_say_one_thing)
        assert label is not None
        assert "light" in label.lower() or "Light" in label

    def test_an_absent_component_contributes_nothing_and_is_not_counted(self) -> None:
        """Missing stays missing here too - never a zero contribution."""
        with_gap = score_with([("present", 50.0, 80.0), ("absent", 50.0, None)])
        label, share = _dominant(with_gap)
        assert label is not None, "the one component that ran carries the whole score"
        assert share == pytest.approx(100.0)

    def test_a_score_with_nothing_available_names_nothing(self) -> None:
        empty = score_with([("a", 50.0, None), ("b", 50.0, None)])
        assert _dominant(empty) == (None, None)


class TestItChangesNothingElse:
    @pytest.fixture(scope="class")
    def api(self) -> TestClient:
        from app.main import app

        with TestClient(app) as client:
            yield client

    def test_the_score_is_untouched_whether_named_or_not(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"limit": 6, "sort": "minutes"}).json()
        for player in body["items"]:
            roles = api.get(f"/api/v1/players/{player['player_id']}/roles").json()
            for role in [roles["best"], *roles["alternatives"]]:
                if role is None or role["score"] is None:
                    continue
                assert 0.0 <= role["score"] <= 100.0
                if role["dominant_component"] is not None:
                    assert role["dominant_share"] >= DOMINANT_CONTRIBUTION

    def test_the_threshold_is_stated_rather_than_hidden(self) -> None:
        import inspect

        from app.api.v1 import players

        source = inspect.getsource(players)
        at = source.index("DOMINANT_CONTRIBUTION = ")
        assert "judgement" in source[max(0, at - 600) : at]
