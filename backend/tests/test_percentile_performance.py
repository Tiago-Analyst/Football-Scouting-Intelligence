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

from app.analytics.metrics import DerivedMetric
from app.analytics.percentiles import (
    ComparisonContext,
    PercentileEngine,
    PercentileScope,
)
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def view():  # type: ignore[no-untyped-def]
    """The loaded universe, for the tests that score players rather than rank them."""
    from app.services.analytics_service import get_analytics_view

    loaded = get_analytics_view()
    if loaded.intelligence is None or len(loaded.players) < 20:
        pytest.skip("needs a loaded population")
    return loaded


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


class TestTheContextIsAssembledOncePerPopulation:
    """The same defect, a second time, in the function beside the first one.

    `_measure_maturity` was memoised and the endpoint was still too slow to
    render. Profiling the fixed version found `_context` doing the same thing
    one call up: collecting the population's competitions into a set and
    sorting them, once per metric per player. Over 7,190 candidates that is
    230,080 walks and 62% of the request.

    The lesson the first fix did not learn is that `_by_group` is walked by
    whoever asks a question about a population, and a question asked inside
    the per-player loop has to be answered outside it.
    """

    def test_ranking_many_players_assembles_few_contexts(
        self, engine: PercentileEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        builds = {"n": 0}
        original = PercentileEngine._build_context

        def counted(self: PercentileEngine, *args: object, **kwargs: object) -> object:
            builds["n"] += 1
            return original(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(PercentileEngine, "_build_context", counted)

        group, season = next(iter(engine._by_group))
        records = engine._by_group[(group, season)]
        if len(records) < 20:
            pytest.skip("needs a populated group")

        ranked = 0
        for record in records[:20]:
            ranked += len(engine.rank_all(record, scope=PercentileScope.GLOBAL))

        assert ranked, "no player produced a ranking"
        # A context is fixed by its population and its size, and twenty
        # players over one population share both: at most a handful of
        # distinct sizes, one per metric. Without the memo this is one build
        # per result - several hundred.
        assert builds["n"] <= len(DerivedMetric), (
            f"assembled {builds['n']} contexts for {ranked} rankings over one population"
        )

    def test_the_memo_answers_what_the_assembly_answers(self, engine: PercentileEngine) -> None:
        """A cache that returns something else is worse than no cache.

        Every field of a `ComparisonContext` has to be determined by the key,
        or a hit answers a different question from a miss. Compared directly
        over real populations rather than argued for in a comment.
        """
        compared = 0
        for (group, season), records in list(engine._by_group.items())[:8]:
            competitions = {r.competition_id for r in records}
            for selected in (None, *(frozenset({c}) for c in sorted(competitions)[:2])):
                for size in (0, 7, len(records)):
                    for scope in (PercentileScope.GLOBAL, PercentileScope.COMPETITION):
                        built = engine._build_context(scope, group, season, selected, size)
                        memoised = engine._context(scope, group, season, selected, size)
                        assert memoised == built, (
                            f"{group}/{season} {selected} size={size}: "
                            f"memo gave {memoised}, assembly gives {built}"
                        )
                        compared += 1
        assert compared, "no population to compare over"

    def test_a_shared_context_cannot_be_mutated_by_one_result(self) -> None:
        """What makes handing one instance to many results safe."""
        assert ComparisonContext.__dataclass_params__.frozen


class TestOnlyTheRequestedScoresAreComputed:
    """Eight scores computed, three read.

    A recruitment brief weights three or five of the eight and the loop reads
    only those. The other five ranked some twenty metrics per candidate for an
    answer nothing would ever look at - three fifths of the percentile work in
    the request, discarded on the way out.

    These are about WHICH scores are computed. The ones that are computed are
    computed identically, which the first test here exists to keep true.
    """

    def test_a_narrowed_result_equals_the_full_one(self, view) -> None:  # type: ignore[no-untyped-def]
        """The whole safety argument for narrowing, asserted on real players.

        A score is a function of one player, one scope and one definition. If
        that holds, taking three of the eight gives the same three objects as
        computing all eight and discarding five - and if it ever stops
        holding, narrowing would silently change a ranking.
        """
        engine = view.intelligence
        wanted = list(engine.definitions)[:3]
        compared = 0
        for key in list(view.players)[:40]:
            metrics = view.player_metrics(key)
            if metrics is None:
                continue
            full = engine.score_all(metrics, scope=PercentileScope.GLOBAL)
            part = engine.score_all(metrics, scope=PercentileScope.GLOBAL, keys=wanted)
            # The full result with entries removed, in the same order: a
            # caller reading "the first score" gets the same score either way.
            assert list(part) == [k for k in full if k in set(wanted)]
            for score_key, score in part.items():
                assert score == full[score_key], f"{key}/{score_key} changed when narrowed"
                compared += 1
        assert compared, "no player produced a score"

    def test_the_search_asks_for_the_weighted_scores_only(self, view) -> None:  # type: ignore[no-untyped-def]
        from fastapi.testclient import TestClient

        from app.core.config import get_settings
        from app.main import create_app
        from tests.conftest import build_settings

        engine_type = type(view.intelligence)
        original = engine_type.score_all
        asked: list[object] = []

        def recording(self, metrics, **kwargs):  # type: ignore[no-untyped-def]
            asked.append(kwargs.get("keys"))
            return original(self, metrics, **kwargs)

        settings = build_settings()
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app, raise_server_exceptions=False)

        weights = {"ball_security": 30, "defensive_activity": 15}
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(engine_type, "score_all", recording)
            response = client.post(
                "/api/v1/recruitment/search",
                json={"weights": weights, "filters": {"position_groups": ["CB"]}, "limit": 20},
            )
        assert response.status_code == 200
        if not asked:
            pytest.skip("no candidate was admitted, so no score was computed")
        for requested in asked:
            assert requested is not None, "the search still asks for every score"
            assert set(requested) == set(weights)

    def test_an_unknown_key_is_refused_rather_than_silently_dropped(self, view) -> None:  # type: ignore[no-untyped-def]
        # A typo that narrowed to nothing would hand `weighted_score` no
        # components at all, and be reported as "no player could be ranked"
        # rather than as the bad request it is.
        from app.analytics.intelligence import ScoreConfigError

        metrics = view.player_metrics(next(iter(view.players)))
        with pytest.raises(ScoreConfigError):
            view.intelligence.score_all(metrics, keys=["ball_security", "not_a_score"])
