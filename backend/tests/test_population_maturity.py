"""What an all-leagues percentile is actually a rank against.

"All covered competitions" reads as a comparison with the wider game. On the
loaded data most of that population has barely started its season, so the
rank is largely against a handful of matches - and how few depends on the
position, since a goalkeeper accumulates minutes faster than a forward.

The percentile is not wrong. It is an honest rank within the population it
names, and nothing here changes a single number. What was missing was any way
for a reader to know what that population is made of, and these hold the
description to being measured from the population itself rather than written
down and left to rot.

The counts that used to open this docstring were written down and left to rot
exactly as that last sentence warns: they said nine of 44 competitions long
after production said otherwise. Dated figures belong in
`docs/methodology.md`; these tests assert the shape, not the numbers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.percentiles import ComparisonContext, PercentileScope
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES
from app.schemas.canonical import PositionGroup


def _maturity_source() -> str:
    """Everything the engine runs to answer "how mature is this population?".

    Two methods rather than one: the measurement is memoised, because running
    it per metric per player cost a recruitment search thirty of its
    thirty-four seconds. The guards below are about the measurement, so they
    read both and do not care which half the work currently sits in.
    """
    import inspect

    from app.analytics import percentiles

    return inspect.getsource(percentiles.PercentileEngine._maturity) + inspect.getsource(
        percentiles.PercentileEngine._measure_maturity
    )


def context(**kwargs: object) -> ComparisonContext:
    base: dict[str, object] = {
        "scope": PercentileScope.GLOBAL,
        "position_group": PositionGroup.CB,
        "season_id": "2026-2027",
        "competition_ids": ("a", "b"),
        "population_size": 100,
        "minimum_minutes": 0,
    }
    base.update(kwargs)
    return ComparisonContext(**base)  # type: ignore[arg-type]


class TestTheNote:
    def test_a_single_competition_says_nothing(self) -> None:
        """A mature league needs no sentence about itself."""
        assert context(competition_ids=("a",), competitions_in_population=1).maturity_note is None

    def test_a_population_where_every_competition_has_played_says_nothing_either(self) -> None:
        note = context(
            competitions_in_population=9, competitions_established=9, established_share=1.0
        ).maturity_note
        assert note is None, "there is nothing to warn about"

    def test_a_mixed_population_says_what_it_is_made_of(self) -> None:
        note = context(
            competitions_in_population=44,
            competitions_established=9,
            established_share=0.28,
            median_minutes=270,
        ).maturity_note
        assert note is not None
        assert "44 competitions" in note
        assert "9 have played enough" in note
        assert "28%" in note
        assert "270 minutes" in note

    def test_it_never_claims_a_league_is_weaker(self) -> None:
        """Maturity is about how much football has been played, not quality.

        This product refuses to rank competitions by strength, and a note
        about early seasons must not become one by accident.
        """
        note = context(
            competitions_in_population=44, competitions_established=9, established_share=0.28
        ).maturity_note
        assert note is not None
        for word in ("weaker", "stronger", "better", "worse", "quality"):
            assert word not in note.lower()

    def test_early_season_needs_more_than_one_competition(self) -> None:
        assert not context(
            competition_ids=("a",), competitions_in_population=1, established_share=0.0
        ).is_early_season

    def test_a_mostly_immature_population_is_flagged(self) -> None:
        assert context(competitions_in_population=44, established_share=0.28).is_early_season
        assert not context(competitions_in_population=44, established_share=0.9).is_early_season


class TestMeasuredFromThePopulation:
    """Not configured, so it cannot go stale as seasons progress."""

    @pytest.fixture(scope="class")
    def api(self) -> TestClient:
        from app.main import app

        with TestClient(app) as client:
            yield client

    def test_a_global_context_reports_its_competitions(self, api: TestClient) -> None:
        player = api.get("/api/v1/players", params={"limit": 1}).json()["items"][0]
        stats = api.get(f"/api/v1/players/{player['player_id']}/stats").json()
        wider = stats.get("global_context")
        if wider is None:
            pytest.skip("no wider population for this player")
        assert wider["competitions_in_population"] >= 1
        assert 0 <= wider["competitions_established"] <= wider["competitions_in_population"]
        assert 0.0 <= wider["established_share"] <= 1.0
        assert wider["median_minutes"] >= 0

    def test_a_competition_scoped_context_is_one_competition(self, api: TestClient) -> None:
        player = api.get("/api/v1/players", params={"limit": 1}).json()["items"][0]
        stats = api.get(f"/api/v1/players/{player['player_id']}/stats").json()
        own = stats.get("context")
        if own is None:
            pytest.skip("no competition population for this player")
        assert own["competitions_in_population"] == 1
        assert own["maturity_note"] is None

    def test_the_threshold_is_the_established_band_not_a_new_one(self) -> None:
        """Borrowed rather than invented, like every other minutes figure."""
        assert "ESTABLISHED_SAMPLE_MINUTES" in _maturity_source()
        assert ESTABLISHED_SAMPLE_MINUTES == 900

    def test_nothing_about_this_changes_a_percentile(self, api: TestClient) -> None:
        """The whole point: the room is described, the rank is untouched."""
        source = _maturity_source()
        for forbidden in ("percentile_of", "oriented", "return None  # excluded"):
            assert forbidden not in source
        # And the population builder is shared, so maturity is measured over
        # exactly the players being ranked.
        assert "_population_for" in source
