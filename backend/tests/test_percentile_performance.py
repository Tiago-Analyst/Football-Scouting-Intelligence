"""The measurements that may not run once per player.

A recruitment search scores every candidate, and every score ranks several
metrics. Anything inside that loop which walks the whole population turns a
linear search into a quadratic one, and nothing in the output says so - the
numbers stay right and the page stops loading.

That is not hypothetical. Season maturity was added to the comparison context
and measured on every call: a brief over 947 candidates called it 30,304
times, each walking the population, and the endpoint took 30 to 60 seconds
against a frontend that waits 30. Every brief that matched anybody failed in
production while the builder, the presets and the empty state all worked.

These are structural rather than timed. A wall-clock ceiling on shared CI
measures the machine as much as the code; counting the walks measures the
thing that actually regressed.
"""

from __future__ import annotations

import pytest

from app.analytics.percentiles import PercentileEngine, PercentileScope
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> PercentileEngine:
    """The real loaded population, because the defect scaled with its size."""
    from app.services.analytics_service import get_analytics_view

    view = get_analytics_view()
    if view.percentiles is None or view.percentiles.eligible_count < 50:
        pytest.skip("needs a loaded population")
    return view.percentiles


class TestMaturityIsMeasuredOncePerPopulation:
    def test_repeated_ranking_does_not_repeat_the_walk(
        self, engine: PercentileEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One walk per population, however many players are ranked over it."""
        walks = {"n": 0}
        original = PercentileEngine._measure_maturity

        def counted(self: PercentileEngine, *args: object, **kwargs: object) -> object:
            walks["n"] += 1
            return original(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(PercentileEngine, "_measure_maturity", counted)

        # A population to rank over, and enough players in it that an
        # unmemoised walk would be obvious.
        group, season = next(iter(engine._by_group))
        records = engine._by_group[(group, season)]
        if len(records) < 20:
            pytest.skip("needs a populated group")

        populations = set()
        for record in records[:20]:
            ranked = engine.rank_all(record, scope=PercentileScope.COMPETITION)
            if not ranked:
                continue
            populations.add(next(iter(ranked.values())).context.competition_ids)

        assert populations, "no player produced a ranking"
        # At most one walk per distinct population touched. Twenty players
        # ranking a dozen metrics each would otherwise be hundreds.
        assert walks["n"] <= len(populations), (
            f"maturity walked the population {walks['n']} times for {len(populations)} populations"
        )

    def test_the_memo_answers_what_the_walk_answers(self, engine: PercentileEngine) -> None:
        """A cache that returns something else is worse than no cache."""
        group, season = next(iter(engine._by_group))
        for competition_ids in (
            None,
            frozenset({engine._by_group[(group, season)][0].competition_id}),
        ):
            measured = engine._measure_maturity(group, season, competition_ids)
            memoised = engine._maturity(group, season, competition_ids)
            assert memoised == measured

    def test_the_threshold_is_still_the_established_band(self) -> None:
        """Guarded here too, so a rewrite for speed cannot quietly move it."""
        import inspect

        source = inspect.getsource(PercentileEngine._measure_maturity)
        assert "ESTABLISHED_SAMPLE_MINUTES" in source
        assert ESTABLISHED_SAMPLE_MINUTES == 900


class TestRecruitmentFitsTheRequestLifecycle:
    """The endpoint the defect actually broke."""

    def test_a_brief_that_matches_people_answers_well_inside_the_timeout(self) -> None:
        import time

        from fastapi.testclient import TestClient

        from app.core.config import get_settings
        from app.main import create_app
        from tests.conftest import build_settings

        settings = build_settings()
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app, raise_server_exceptions=False)

        body = {
            "weights": {"ball_security": 30, "defensive_activity": 15},
            "filters": {"position_groups": ["CB"], "min_minutes": 0},
            "limit": 20,
        }
        # The analytical view is built once per process; that cost belongs to
        # startup, not to a search.
        warm = client.post("/api/v1/recruitment/search", json=body)
        assert warm.status_code == 200
        if not warm.json()["items"]:
            pytest.skip("no candidate matched; this test is about a populated search")

        started = time.perf_counter()
        response = client.post("/api/v1/recruitment/search", json=body)
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        # The frontend gives up at thirty seconds. Ten leaves room for a
        # slower machine without letting a quadratic loop back in: the
        # defective version took fourteen on this data and fifty in
        # production.
        assert elapsed < 10.0, f"a recruitment brief took {elapsed:.1f}s"
